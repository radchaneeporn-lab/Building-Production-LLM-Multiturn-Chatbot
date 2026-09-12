
# this file is for learning about sys.argv that will be used in main_service.py 
import sys
print("argv is:", sys.argv)

# sys is just a module in the standard library that holds things belonging to the running process itself rather than to your program's logic — the arguments it was started with (sys.argv), a way to quit (sys.exit), the input and output streams. That's all import sys means. Nothing magic.
# run these command in the terminal
# python scratch.py
# python scratch.py hello
# python scratch.py hello world

# you'll get'
# argv is: ['scratch.py']
# argv is: ['scratch.py', 'hello']
# argv is: ['scratch.py', 'hello', 'world']

# Position 0 is always the script name, so anything you typed starts at position 1. That's why the CLI says:
# if len(sys.argv) > 1:
#     session_id = sys.argv[1]