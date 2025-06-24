#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import List, Set, Dict
import requests
from requests.auth import HTTPBasicAuth

def extract_jira_tickets_from_release_notes(release_body: str) -> Set[str]:
    """リリースノートからJIRAチケット番号を抽出"""
    pattern = r'\[?(WOR-\d+)\]?'
    tickets = re.findall(pattern, release_body)
    return set(tickets)

def extract_fix_version_from_release_name(release_name: str) -> str:
    """リリース名からfix versionを抽出（例: v3.13.8-0 -> 11399）"""
    # この部分は実際のJIRAのversion IDマッピングに応じて調整が必要
    # 仮実装として、環境変数でマッピングを管理
    version_mapping = json.loads(os.environ.get('JIRA_VERSION_MAPPING', '{}'))
    
    # リリース名からバージョン番号を抽出
    version_match = re.search(r'v?(\d+\.\d+\.\d+)', release_name)
    if version_match:
        version = version_match.group(1)
        return version_mapping.get(version, '')
    return ''

def get_jira_tickets_from_api(fix_version: str) -> Set[str]:
    """JIRA APIからfix versionに紐づくチケットを取得"""
    jira_base_url = os.environ.get('JIRA_BASE_URL', 'https://omnisinc.atlassian.net')
    jira_email = os.environ.get('JIRA_EMAIL')
    jira_api_token = os.environ.get('JIRA_API_TOKEN')
    
    if not all([jira_email, jira_api_token]):
        print("Error: JIRA credentials not found in environment variables")
        return set()
    
    auth = HTTPBasicAuth(jira_email, jira_api_token)
    
    # JQL query to get issues with specific fix version
    jql = f"project = WOR AND fixversion = {fix_version} ORDER BY created DESC"
    
    url = f"{jira_base_url}/rest/api/2/search"
    params = {
        'jql': jql,
        'fields': 'key',
        'maxResults': 999
    }
    
    try:
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        
        data = response.json()
        tickets = {issue['key'] for issue in data.get('issues', [])}
        return tickets
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching JIRA tickets: {e}")
        return set()

def compare_tickets(release_tickets: Set[str], jira_tickets: Set[str]) -> Dict[str, Set[str]]:
    """リリースノートとJIRAのチケットを比較"""
    return {
        'only_in_release': release_tickets - jira_tickets,
        'only_in_jira': jira_tickets - release_tickets,
        'common': release_tickets & jira_tickets
    }

def send_slack_notification(message: str, webhook_url: str):
    """Slackに通知を送信"""
    payload = {
        'text': message,
        'unfurl_links': True,
        'unfurl_media': True
    }
    
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print("Slack notification sent successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Slack notification: {e}")

def format_slack_message(comparison: Dict[str, Set[str]], release_url: str, release_name: str) -> str:
    """Slack通知用のメッセージをフォーマット"""
    message_parts = [
        f"🔍 *リリースドラフト検証結果*",
        f"リリース: <{release_url}|{release_name}>",
        ""
    ]
    
    if comparison['only_in_release']:
        message_parts.append("⚠️ *リリースノートのみに存在するチケット:*")
        for ticket in sorted(comparison['only_in_release']):
            jira_url = f"{os.environ.get('JIRA_BASE_URL', 'https://omnisinc.atlassian.net')}/browse/{ticket}"
            message_parts.append(f"  • <{jira_url}|{ticket}>")
        message_parts.append("")
    
    if comparison['only_in_jira']:
        message_parts.append("❌ *JIRAのみに存在するチケット:*")
        for ticket in sorted(comparison['only_in_jira']):
            jira_url = f"{os.environ.get('JIRA_BASE_URL', 'https://omnisinc.atlassian.net')}/browse/{ticket}"
            message_parts.append(f"  • <{jira_url}|{ticket}>")
        message_parts.append("")
    
    if not comparison['only_in_release'] and not comparison['only_in_jira']:
        message_parts.append("✅ リリースノートとJIRAのチケットは完全に一致しています")
    else:
        message_parts.append(f"📊 共通のチケット数: {len(comparison['common'])}")
    
    return "\n".join(message_parts)

def main():
    parser = argparse.ArgumentParser(description='Verify JIRA tickets in release draft')
    parser.add_argument('--release-body', required=True, help='Release body content')
    parser.add_argument('--release-name', required=True, help='Release name')
    parser.add_argument('--release-url', required=True, help='Release URL')
    parser.add_argument('--fix-version', help='JIRA fix version (optional, will try to extract from release name)')
    
    args = parser.parse_args()
    
    # リリースノートからチケット番号を抽出
    release_tickets = extract_jira_tickets_from_release_notes(args.release_body)
    print(f"Found {len(release_tickets)} tickets in release notes: {sorted(release_tickets)}")
    
    # Fix versionを取得（引数で指定されていない場合は、リリース名から推測）
    fix_version = args.fix_version or extract_fix_version_from_release_name(args.release_name)
    
    if not fix_version:
        # Fix versionが見つからない場合は、環境変数でデフォルト値を設定可能
        fix_version = os.environ.get('DEFAULT_FIX_VERSION', '')
        if not fix_version:
            print("Warning: Could not determine fix version. Please set DEFAULT_FIX_VERSION environment variable or provide --fix-version argument.")
            sys.exit(1)
    
    print(f"Using fix version: {fix_version}")
    
    # JIRA APIからチケットを取得
    jira_tickets = get_jira_tickets_from_api(fix_version)
    print(f"Found {len(jira_tickets)} tickets in JIRA: {sorted(jira_tickets)}")
    
    # チケットを比較
    comparison = compare_tickets(release_tickets, jira_tickets)
    
    # 結果を出力
    print("\n=== Comparison Results ===")
    print(f"Only in release notes: {sorted(comparison['only_in_release'])}")
    print(f"Only in JIRA: {sorted(comparison['only_in_jira'])}")
    print(f"Common tickets: {len(comparison['common'])}")
    
    # Slack通知を送信
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if slack_webhook_url and (comparison['only_in_release'] or comparison['only_in_jira']):
        message = format_slack_message(comparison, args.release_url, args.release_name)
        send_slack_notification(message, slack_webhook_url)
    elif not slack_webhook_url:
        print("Warning: SLACK_WEBHOOK_URL not set, skipping Slack notification")
    
    # 不一致がある場合は終了コード1で終了
    if comparison['only_in_release'] or comparison['only_in_jira']:
        sys.exit(1)
    
    print("\n✅ All tickets match between release notes and JIRA!")

if __name__ == '__main__':
    main()