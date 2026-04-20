import pickle
import os
from pyicloud import PyiCloudService

# Configuration
APPLE_ID = 'XXXXX@icloud.com'
PASSWORD = 'XXXXXXXXXX'
TOKEN_FILE = 'icloud_token.bin'

def generate_persistent_token():
    # 1. Initialize the service
    # We use a temp directory to handle the initial handshake
    api = PyiCloudService(APPLE_ID, PASSWORD)

    # 2. Handle 2FA (The 'Trust' handshake)
    if api.requires_2fa:
        print("2FA is required.")
        devices = api.trusted_devices
        for i, device in enumerate(devices):
            print(f"  {i}: {device.get('deviceName', 'Unknown device')}")
        
        device_index = int(input("Select device index to receive code: "))
        device = devices[device_index]
        
        if not api.send_verification_code(device):
            print("Failed to send verification code")
            return

        code = input("Enter the code you received: ")
        if not api.validate_2fa_code(code):
            print("Failed to verify code")
            return

        # 3. CRITICAL: Trust this session to make it last 30 days
        print("Trusting session...")
        api.trust_session()

    # 4. Extract the Cookie Jar and Pickle it
    # This 'cookie_bytes' contains the MFA trust and session tokens
    cookie_bytes = pickle.dumps(api.session.cookies)
    
    with open(TOKEN_FILE, 'wb') as f:
        f.write(cookie_bytes)
    
    print(f"\nSUCCESS!")
    print(f"Token saved to: {TOKEN_FILE}")
    print("You can now use: session_cookies = pickle.loads(cookie_bytes) in your other code.")

if __name__ == "__main__":
    generate_persistent_token()