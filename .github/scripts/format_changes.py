import sys

def format_changes(changes):
    formatted_lines = []
    for line in changes.split(r'\r\n'):
        # Replace * with -
        line = line.replace(r'*', '-')
        
        # Remove "by @username" and the URL until the end of the line
        if ' by @' in line:
            line = line.split(' by @')[0]
        
        formatted_lines.append(line)
    
    formatted_changes = r'\r\n'.join(formatted_lines)
    
    # Remove everything after "--Full Changelog--"
    if '--Full Changelog--' in formatted_changes:
        formatted_changes = formatted_changes.split('--Full Changelog--')[0]
    
    return formatted_changes.rstrip(r'\r\n')

if __name__ == "__main__":
    changes = sys.argv[1]
    formatted_changes = format_changes(changes)
    
    print(formatted_changes)