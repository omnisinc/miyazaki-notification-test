#!/usr/bin/env python3
import sys
import re

def extract_changed_section(content):
    """Extract only the Changed section from release notes"""
    # Look for ## Changed section
    changed_pattern = r'## What\'s Changed\s*(.*?)(?=##|$)'
    changed_match = re.search(changed_pattern, content, re.DOTALL)
    
    if changed_match:
        return changed_match.group(1).strip()
    return ""

def format_changes(changes):
    formatted_lines = []
    
    for line in changes.split('\n'):
        # Skip empty lines
        if not line.strip():
            continue
        
        # First, convert PR URLs to markdown format before removing by @username
        # https://github.com/org/repo/pull/123 -> [#123](https://github.com/org/repo/pull/123)
        def replace_pr_url(match):
            url = match.group(0)
            pr_number = match.group(1)
            return f'[#{pr_number}]({url})'
        
        pr_url_pattern = r'https://github\.com/[\w-]+/[\w-]+/pull/(\d+)'
        line = re.sub(pr_url_pattern, replace_pr_url, line)
        
        # Then remove " by @username" (but PR URL is already converted to markdown)
        if ' by @' in line:
            line = re.sub(r'\s+by\s+@[\w-]+', '', line)
        
        # * を - に置換 (Slack doesn't handle * well in lists)
        if line.strip().startswith('*'):
            line = line.replace('*', '-', 1)
        
        # WOR-1758 のような文字列が含まれている場合、Slack の mrkdwn 文字列に変換
        line = re.sub(r'(WOR-\d+)', r'<https://omnisinc.atlassian.net/browse/\1|\1>', line)
        
        # Escape for JSON
        line = line.replace('\\', '\\\\')  # Escape backslashes
        line = line.replace('"', '\\"')    # Escape double quotes
        
        formatted_lines.append(line)
    
    # Join with escaped newlines for JSON
    return '\\n'.join(formatted_lines)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python format_release_changes.py <release_body_file>")
        sys.exit(1)
    
    # Read from file
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract Changed section
    changed_content = extract_changed_section(content)
    
    if changed_content:
        formatted_changes = format_changes(changed_content)
        print(formatted_changes)
    else:
        print("No changes found")