import sys


def main():
    while True:
        sys.stdout.write("$ ")
        input_str = input().strip()
        command = input_str.split(" ", 1)[0]
        args = input_str.split(" ", 1)[1] if len(input_str.split(" ", 1)) > 1 else None
        
        supported_commands = ["exit", "echo", "help", "type"]
        
        def cmd_echo(args):
            print(args)
        
        def cmd_help(_args):
            print("Available commands:", " ".join(sorted(supported_commands)))
        
        def cmd_type(args):
            if args in supported_commands:
                print(f"{args} is a shell builtin")
            else:
                print(f"{args}: not found")
                
        handlers = {
            "echo": cmd_echo,
            "help": cmd_help,
            "type": cmd_type,
        }

        if command == "exit":
            break

        handler = handlers.get(command)
        if handler:
            handler(args)
        else:
            print(f"{command}: command not found")


if __name__ == "__main__":
    main()
