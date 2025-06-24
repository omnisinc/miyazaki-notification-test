import sys
import re

def format_changes(changes):
    formatted_lines = []
    code_block_started = False
    prev_is_jira = False
    for line in changes.split(r'\r\n'):
        # "**Full Changelog" 以降のすべてを削除
        if line.startswith('**Full Changelog'):
            break

        # ##JIRA の場合、次の行をスキップしてリンクにする
        if line.startswith('## JIRA'):
            prev_is_jira = True
            continue
        if prev_is_jira:
            line = f'<{line}|JIRA Release>'
            formatted_lines.append(line)
            prev_is_jira=False
            continue

        # " by @username" とその行の最後までの URL を削除
        if ' by @' in line:
            line = line.split(' by @')[0]
        
        # * を - に置換
        line = line.replace(r'*', '-')

        # ## を *text* に置換
        if line.startswith('##'):
            line = '*' + line.replace('##', '').strip() + '*'
        
        # WOR-1758 のような文字列が含まれている場合、Slack の mrkdwn 文字列に変換
        line = re.sub(r'(WOR-\d+)', r'<https://omnisinc.atlassian.net/browse/\1|\1>', line)

        formatted_lines.append(line)

        # What's Changed 配下はコードブロックにする
        if line == "*What's Changed*":
            formatted_lines.append('```')
    
    formatted_changes = r'\r\n'.join(formatted_lines)
    formatted_changes = formatted_changes.rstrip(r'\r\n')
    formatted_changes = formatted_changes + (r'\r\n```')
    
    return formatted_changes

if __name__ == "__main__":
    changes = sys.argv[1]
    formatted_changes = format_changes(changes)
    
    print(formatted_changes)