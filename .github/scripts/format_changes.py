import sys

def format_changes(changes):
    formatted_lines = []
    code_block_started = False
    for line in changes.split(r'\r\n'):
        # Remove everything after "--Full Changelog--"
        if line.startswith('**Full Changelog'):
            break

        # Remove "by @username" and the URL until the end of the line
        if ' by @' in line:
            line = line.split(' by @')[0]
        
        # Replace * with -
        line = line.replace(r'*', '-')

        # Replace ## with *text*
        if line.startswith('##'):
            line = '*' + line.replace('##', '').strip() + '*'

        formatted_lines.append(line)

        if line == "*What's Changed*":
            formatted_lines.append('```')
    
    formatted_lines.append('```') 
    formatted_changes = r'\r\n'.join(formatted_lines)
    
    return formatted_changes.rstrip(r'\r\n')

if __name__ == "__main__":
    changes = sys.argv[1]
    formatted_changes = format_changes(changes)
    
    print(formatted_changes)