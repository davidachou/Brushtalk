# Brushtalk (筆談)

Brushtalk turns what you say into text you can use: notes from a call, notes from talking to yourself, a prompt to paste into an AI
chat, a piece of code, or a proofread of something you copied. It runs on your own PC. It's a personal tool, shared as it is, not a
product.

## What you need

- **Windows 11** and a microphone. A headset is best on calls.
- **An NVIDIA graphics card** makes turning speech into text fast. Without one it still works, on the processor, but takes much longer.
- **For notes, prompts, code and proofreading:** a paid ChatGPT plan (Plus or above), to use Codex, or a paid Claude plan (Pro or
  above), to use Claude Code. One is enough. Without either, Brushtalk still records and makes transcripts.
- About **3 GB** of space for Brushtalk itself, plus your recordings: an hour of a call takes about 50 MB.

## Setting it up

1. **Download it.** On this page, press the green **Code** button, then **Download ZIP**. If someone gave you the zip, use that.
2. **Unblock the download.** Right-click the zip, choose **Properties**, tick **Unblock** at the bottom, then **OK**. Without this,
   Windows may stop the setup from running.
3. **Unzip it somewhere it can stay**, such as your Documents folder. Your recordings will be kept inside it, in a folder called `data`.
4. **Double-click `Set up Brushtalk`.** If Windows asks whether to run it, choose **Run**. It installs Python 3.13 if your PC doesn't
   have it, then what Brushtalk needs (about 1.2 GB), then Whisper, the speech model (about 1.6 GB), then shortcuts in the Start menu
   and on the desktop. The first time takes a while. At the end it shows what's ready on your PC.
5. **For notes and prompts**, the setup says what to install and how to sign in, if Codex or Claude Code isn't there yet. Do that,
   then run `Set up Brushtalk` again to check.

## Using it

Open **Brushtalk** from the Start menu. It lives in the tray, by the clock, so the shortcuts work while you're in other apps.

| | Records | Shortcut | You get |
|---|---|---|---|
| **Meeting** | Your mic and your computer's sound | Ctrl+Alt+R | Notes |
| **Solo note** | Only your mic | Ctrl+Alt+N | Notes |
| **Prompt** | Your mic, and text you copy | Ctrl+Alt+D | A prompt, ready to paste |
| **Code** | Your mic, and text you copy | Ctrl+Alt+C | The code, ready to paste |
| **Proofread** | Text you copy, and your mic if you want to say how | Ctrl+Alt+P | The edited text, ready to paste |

Press a shortcut again to pause, or to stop a meeting. **Ctrl+Alt+Enter** finishes whichever is going, and
**Ctrl+Alt+Shift+P** proofreads what you just copied without listening. Everything else is in **Settings**: the microphone, the
shortcuts, which AI writes, Traditional or Simplified Chinese, the look and the sounds. The checks at the top of Settings say if
anything's missing.

## Your privacy

- Your audio stays on your PC.
- Only the transcript, and anything you copy into a prompt, goes to the AI you chose, under your own ChatGPT or Claude account.
- **Tell people before you record a call.** The recording screen has a **Copy a notice** button for the chat.

## Updating and removing

- **To update**, download the new version the same way, unzip it over the old folder, then run `Set up Brushtalk` again. Your
  recordings, in `data`, stay.
- **To remove it**, quit Brushtalk from the tray, then delete its folder and its shortcuts. Copy the `data` folder first if you want
  to keep your recordings and notes.

Stuck? Ask whoever gave you Brushtalk.
