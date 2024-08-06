import re
import sys

def format_changes(changes):
    # Remove carriage returns
    changes = changes.replace('\r', '')
    
    # Replace * with -
    changes = re.sub(r'\*', '-', changes)
    
    # Remove "by @username" until the end of the line
    changes = re.sub(r' by @.*$', '', changes, flags=re.MULTILINE)
    
    return changes

if __name__ == "__main__":
    changes = sys.argv[1]
    formatted_changes = format_changes(changes)
    
    print(formatted_changes)
