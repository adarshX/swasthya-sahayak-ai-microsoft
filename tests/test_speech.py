"""
TEST: Azure AI Speech
Uses the Speech REST API directly — no SDK install required.
Checks: key valid, region reachable, text-to-speech synthesis works,
        speech-to-text token endpoint works.
Run:  python tests/test_speech.py
"""

import os
import sys

def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

load_env()
# Also check local.properties for Android-placed keys
def load_local_properties(path="android-app/local.properties"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

load_local_properties()

SPEECH_KEY    = os.getenv("AZURE_SPEECH_KEY", "")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

def main():
    print("\n=== Azure AI Speech Test ===\n")

    if not SPEECH_KEY or not SPEECH_REGION:
        print(f"{FAIL}  AZURE_SPEECH_KEY or AZURE_SPEECH_REGION not set")
        print(f"       Add them to android-app/local.properties:")
        print(f"         AZURE_SPEECH_KEY=<KEY 1 from your Azure AI Services resource>")
        print(f"         AZURE_SPEECH_REGION=eastasia")
        sys.exit(1)

    print(f"{INFO}  Key: {SPEECH_KEY[:6]}...{SPEECH_KEY[-4:]}")
    print(f"{INFO}  Region: {SPEECH_REGION}\n")

    try:
        import urllib.request
        import urllib.error
    except ImportError:
        pass  # stdlib, always available

    results = []

    # Test 1: Get auth token (validates key + region)
    try:
        token_url = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
        req = urllib.request.Request(
            token_url,
            data=b"",
            headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            token = resp.read().decode("utf-8")
        print(f"{PASS}  Auth token issued (key + region are valid)")
        print(f"       Token preview: {token[:30]}...")
        results.append(True)
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 401:
            print(f"{FAIL}  Auth failed (401) — AZURE_SPEECH_KEY is wrong")
        elif code == 403:
            print(f"{FAIL}  Forbidden (403) — key may be expired or quota exceeded")
        else:
            print(f"{FAIL}  HTTP {code} from token endpoint")
        results.append(False)
        token = None
    except Exception as e:
        print(f"{FAIL}  Could not reach Speech endpoint -> {e}")
        results.append(False)
        token = None

    # Test 2: Text-to-Speech synthesis (short phrase)
    print()
    try:
        tts_url = f"https://{SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = """<speak version='1.0' xml:lang='en-IN'>
            <voice name='en-IN-NeerjaNeural'>
                Swasthya Sahayak is ready.
            </voice>
        </speak>"""
        req = urllib.request.Request(
            tts_url,
            data=ssml.encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": SPEECH_KEY,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                "User-Agent": "SwasthyaSahayakTest",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            audio_bytes = resp.read()
        kb = len(audio_bytes) / 1024
        print(f"{PASS}  Text-to-Speech synthesis worked -> {kb:.1f} KB of audio returned")
        # Save for manual verification
        out_path = "tests/tts_output.mp3"
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"       Audio saved to {out_path} — play it to verify voice quality")
        results.append(True)
    except Exception as e:
        print(f"{FAIL}  Text-to-Speech failed -> {e}")
        results.append(False)

    # Test 3: Speech-to-Text token endpoint reachable
    print()
    try:
        stt_url = f"https://{SPEECH_REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=hi-IN"
        # Just check endpoint is reachable with a HEAD-like OPTIONS (won't send audio)
        req = urllib.request.Request(
            stt_url,
            data=b"",
            headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            # 400 = endpoint reachable but we sent no audio — that's expected and fine
            if e.code == 400:
                print(f"{PASS}  Speech-to-Text endpoint reachable (400 = no audio sent, expected)")
                results.append(True)
            else:
                raise
    except Exception as e:
        print(f"{FAIL}  Speech-to-Text endpoint check failed -> {e}")
        results.append(False)

    print(f"\n{'='*35}")
    passed = sum(results)
    print(f"  Result: {passed}/{len(results)} checks passed")
    if passed == len(results):
        print(f"\033[92m  Azure AI Speech is correctly configured.\033[0m\n")
    else:
        print(f"\033[91m  Azure AI Speech has issues — check errors above.\033[0m\n")

if __name__ == "__main__":
    main()
