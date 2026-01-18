import sys


def main():
    while True:
        sys.stdout.write("$ ")
        input_str = input()
        if input_str == "exit":
            break
        else:
            print(f"{input_str}: command not found")


if __name__ == "__main__":
    main()
