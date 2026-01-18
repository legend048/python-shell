import sys
import shlex
import shutil
import subprocess
import os


def main():
    builtin_commands = ["exit", "echo", "help", "type", "pwd", "cd"]
    
    def cmd_echo(argv):
        print(" ".join(argv))
    
    def cmd_help(_argv):
        print("Available commands:", " ".join(sorted(builtin_commands)))
    
    def cmd_type(argv):
        if not argv:
            print("type: missing operand")
            return
    
        name = argv[0]
        if name in builtin_commands:
            print(f"{name} is a shell builtin")
            return
    
        path = shutil.which(name)
        if path:
            print(f"{name} is {path}")
        else:
            print(f"{name}: not found")
    
    def cmd_pwd(_argv):
        print(os.getcwd())
    
    def cmd_cd(argv):
        if not argv:
            print("cd: missing operand")
            return
    
        path = argv[0]
        try:
            if path == "~":
                path = os.path.expanduser("~")
            os.chdir(path)
        except FileNotFoundError:
            print(f"cd: {path}: No such file or directory")
    
    def cmd_ls(argv):
        if not argv:
            print("ls: missing operand")
            return
    
        path = argv[0]
        try:
            files = os.listdir(path)
            print("\n".join(files))
        except FileNotFoundError:
            print(f"ls: {path}: No such file or directory")
            
    handlers = {
        "echo": cmd_echo,
        "help": cmd_help,
        "type": cmd_type,
        "pwd": cmd_pwd,
        "cd": cmd_cd,
        "ls": cmd_ls
    }
    
    while True:
        try:
            sys.stdout.write("$ ")
            line = input().strip()
        except EOFError:
            break
    
        if not line:
            continue
    
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            print(f"parse error: {e}")
            continue
    
        command, argv = tokens[0], tokens[1:]
    
        if command == "exit":
            break
    
        handler = handlers.get(command)
        if handler:
            handler(argv)
            continue
    
        exe = shutil.which(command)
        if not exe:
            print(f"{command}: command not found")
            continue
    
        try:
            # you can both spawn a new process or execute the command directly
            # subprocess.run([exe, *argv], executable=exe)
            os.system(line)
        except PermissionError:
            print(f"{command}: permission denied")
        except OSError as e:
            print(f"{command}: failed to execute ({e})")


if __name__ == "__main__":
    main()
