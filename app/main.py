import sys
import shutil
import subprocess
import os
import contextlib

try:
    import readline  # Linux/macOS
except Exception:
    readline = None

if readline is None and os.name == "nt":
    try:
        import pyreadline3 as readline  # Windows fallback
    except Exception:
        readline = None
        
import glob


def _scan_path_executables():
    """Return a set of executable basenames from PATH (best-effort, cached per run)."""
    exes = set()
    path_env = os.environ.get("PATH", "")
    for d in path_env.split(os.pathsep):
        if not d:
            continue
        try:
            for name in os.listdir(d):
                p = os.path.join(d, name)
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    exes.add(name)
        except OSError:
            pass
    return exes


def _in_quotes(line: str, idx: int) -> tuple[bool, str | None]:
    """
    Roughly determine whether cursor at idx is inside single/double quotes.
    Returns (in_quotes, quote_char_or_None).
    """
    in_single = False
    in_double = False
    escape = False
    for i, c in enumerate(line[:idx]):
        if escape:
            escape = False
            continue
        if not in_single and c == "\\":
            escape = True
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            continue
    if in_single:
        return True, "'"
    if in_double:
        return True, '"'
    return False, None


def _escape_if_needed(s: str, line: str, begidx: int) -> str:
    """If not inside quotes, escape spaces so readline inserts safely."""
    inside, _q = _in_quotes(line, begidx)
    if inside:
        return s
    return s.replace(" ", r"\ ")


def _complete_paths(text: str, line: str, begidx: int) -> list[str]:
    """
    Complete filesystem paths (relative/absolute/~).
    Adds trailing '/' for directories.
    """
    if not text:
        text = ""

    typed = text
    typed_starts_tilde = typed.startswith("~")

    expanded = os.path.expanduser(typed)

    pattern = expanded + "*"
    matches = glob.glob(pattern)

    out = []
    home = os.path.expanduser("~")

    for m in sorted(matches):
        disp = m

        if os.path.isdir(m) and not m.endswith(os.sep):
            disp = m + os.sep

        if typed_starts_tilde and disp.startswith(home):
            disp = "~" + disp[len(home):]

        if not typed_starts_tilde and not os.path.isabs(typed):
            try:
                disp = os.path.relpath(disp, os.getcwd())
            except Exception:
                pass

        out.append(_escape_if_needed(disp, line, begidx))

    return out


def setup_autocomplete(builtin_commands: list[str]):
    """Enable TAB completion for commands + paths."""
    if readline is None:
        return
    if not sys.stdin.isatty():
        return

    path_exes = _scan_path_executables()
    builtin_set = set(builtin_commands)

    readline.set_completer_delims(" \t\n><")

    def completer(text: str, state: int):
        line = readline.get_line_buffer()
        begidx = readline.get_begidx()
    
        before = line[:begidx]
        completing_command = (before.strip() == "")
    
        if completing_command:
            if text.startswith(("/", "./", "../", "~")):
                candidates = _complete_paths(text, line, begidx)
            else:
                pool = sorted(builtin_set | path_exes)
                candidates = [_escape_if_needed(x, line, begidx) for x in pool if x.startswith(text)]
    
            if len(candidates) == 1 and not candidates[0].endswith(" "):
                candidates = [candidates[0] + " "]
    
        else:
            candidates = _complete_paths(text, line, begidx)
    
            if len(candidates) == 1:
                c = candidates[0]
                if not (c.endswith("/") or c.endswith(os.sep)):
                    candidates = [c + " "]
    
        return candidates[state] if state < len(candidates) else None

    readline.set_completer(completer)

    doc = readline.__doc__ or ""
    if "libedit" in doc:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    readline.parse_and_bind("set show-all-if-ambiguous on")
    readline.set_completer(completer)

    doc = readline.__doc__ or ""
    if "libedit" in doc:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    readline.parse_and_bind("set show-all-if-ambiguous on")


def tokenize_with_redirs(line: str) -> list[str]:
    tokens = []
    buf = []
    i = 0
    in_single = False
    in_double = False
    escape = False

    def flush_buf():
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    while i < len(line):
        c = line[i]

        if escape:
            buf.append(c)
            escape = False
            i += 1
            continue

        if not in_single and not in_double and c == "\\":
            escape = True
            i += 1
            continue

        if in_single:
            if c == "'":
                in_single = False
            else:
                buf.append(c)
            i += 1
            continue

        if in_double:
            if c == '"':
                in_double = False
                i += 1
                continue

            if c == "\\":
                if i + 1 < len(line):
                    nxt = line[i + 1]
                    if nxt in ['\\', '"', '$', '`', '\n']:
                        buf.append(nxt)
                        i += 2
                        continue
                buf.append("\\")
                i += 1
                continue

            buf.append(c)
            i += 1
            continue

        if c.isspace():
            flush_buf()
            i += 1
            continue

        if c == "'":
            in_single = True
            i += 1
            continue

        if c == '"':
            in_double = True
            i += 1
            continue

        if c == ">":
            fd_prefix = "".join(buf) if buf and all(ch.isdigit() for ch in buf) else None
            if fd_prefix is None:
                flush_buf()
            else:
                buf.clear()

            if i + 1 < len(line) and line[i + 1] == ">":
                op = ">>"
                i += 2
            else:
                op = ">"
                i += 1

            tokens.append((fd_prefix + op) if fd_prefix is not None else op)
            continue

        buf.append(c)
        i += 1

    if in_single or in_double:
        raise ValueError("unclosed quote")

    if escape:
        buf.append("\\")

    flush_buf()
    return tokens


def parse_redirections(argv_tokens: list[str]):
    """
    Returns: (argv, stdout_path, stdout_mode, stderr_path, stderr_mode)
    Supports: >, >>, 1>, 1>>, 2>, 2>>
    """
    argv = []
    stdout_path = None
    stdout_mode = "w"
    stderr_path = None
    stderr_mode = "w"

    i = 0
    while i < len(argv_tokens):
        t = argv_tokens[i]

        def need_target():
            if i + 1 >= len(argv_tokens):
                raise ValueError(f"syntax error near unexpected token `{t}`")
            return argv_tokens[i + 1]

        if t in (">", "1>"):
            stdout_path = need_target()
            stdout_mode = "w"
            i += 2
            continue

        if t in (">>", "1>>"):
            stdout_path = need_target()
            stdout_mode = "a"
            i += 2
            continue

        if t == "2>":
            stderr_path = need_target()
            stderr_mode = "w"
            i += 2
            continue

        if t == "2>>":
            stderr_path = need_target()
            stderr_mode = "a"
            i += 2
            continue

        argv.append(t)
        i += 1

    return argv, stdout_path, stdout_mode, stderr_path, stderr_mode


@contextlib.contextmanager
def redirected_streams(stdout_path, stdout_mode, stderr_path, stderr_mode):
    out_f = open(stdout_path, stdout_mode, encoding="utf-8") if stdout_path else None
    err_f = open(stderr_path, stderr_mode, encoding="utf-8") if stderr_path else None
    try:
        with (contextlib.redirect_stdout(out_f) if out_f else contextlib.nullcontext()):
            with (contextlib.redirect_stderr(err_f) if err_f else contextlib.nullcontext()):
                yield
    finally:
        if out_f:
            out_f.close()
        if err_f:
            err_f.close()


def main():
    builtin_commands = ["exit", "echo", "help", "type", "pwd", "cd", "ls"]

    setup_autocomplete(builtin_commands)

    def eprint(*a, **k):
        print(*a, file=sys.stderr, **k)

    def cmd_echo(argv):
        print(" ".join(argv))

    def cmd_help(_argv):
        print("Available commands:", " ".join(sorted(builtin_commands)))

    def cmd_type(argv):
        if not argv:
            eprint("type: missing operand")
            return
        name = argv[0]
        if name in builtin_commands:
            print(f"{name} is a shell builtin")
            return
        path = shutil.which(name)
        if path:
            print(f"{name} is {path}")
        else:
            eprint(f"{name}: not found")

    def cmd_pwd(_argv):
        print(os.getcwd())

    def cmd_cd(argv):
        if not argv:
            eprint("cd: missing operand")
            return
        path = argv[0]
        if path == "~":
            path = os.path.expanduser("~")
        try:
            os.chdir(path)
        except FileNotFoundError:
            eprint(f"cd: {path}: No such file or directory")

    def cmd_ls(argv):
        path = argv[0] if argv else "."
        try:
            for name in os.listdir(path):
                print(name)
        except FileNotFoundError:
            eprint(f"ls: {path}: No such file or directory")

    handlers = {
        "echo": cmd_echo,
        "help": cmd_help,
        "type": cmd_type,
        "pwd": cmd_pwd,
        "cd": cmd_cd,
        # "ls": cmd_ls,
    }

    while True:
        try:
            sys.stdout.write("$ ")
            line = input()
        except EOFError:
            break

        line = line.strip()
        if not line:
            continue

        try:
            tokens = tokenize_with_redirs(line)
        except ValueError as e:
            eprint(f"parse error: {e}")
            continue

        command = tokens[0]
        raw_argv = tokens[1:]

        if command == "exit":
            break

        try:
            argv, out_path, out_mode, err_path, err_mode = parse_redirections(raw_argv)
        except ValueError as e:
            eprint(str(e))
            continue

        handler = handlers.get(command)
        if handler:
            with redirected_streams(out_path, out_mode, err_path, err_mode):
                handler(argv)
            continue

        if "/" in command:
            exe = command
        else:
            exe = shutil.which(command)

        if not exe:
            with redirected_streams(out_path, out_mode, err_path, err_mode):
                eprint(f"{command}: command not found")
            continue

        out_f = open(out_path, out_mode) if out_path else None
        err_f = open(err_path, err_mode) if err_path else None
        try:
            subprocess.run(
                [command, *argv],
                executable=exe,
                stdout=out_f if out_f else None,
                stderr=err_f if err_f else None,
            )
        except PermissionError:
            with redirected_streams(out_path, out_mode, err_path, err_mode):
                eprint(f"{command}: permission denied")
        except OSError as e:
            with redirected_streams(out_path, out_mode, err_path, err_mode):
                eprint(f"{command}: failed to execute ({e})")
        finally:
            if out_f:
                out_f.close()
            if err_f:
                err_f.close()


if __name__ == "__main__":
    main()
