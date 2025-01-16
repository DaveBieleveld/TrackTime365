from calendar_sync import CalendarSync

def main():
    cs = CalendarSync()
    users = cs.get_users_batch()
    
    print("\nUsers found:")
    for user in users:
        print(f"- {user.get('displayName', 'No Name')} ({user.get('mail', 'No Email')})")

if __name__ == "__main__":
    main() 