# EnaTwitch.py
import json
import datetime
import openai
import os
import asyncio
from dotenv import load_dotenv
from twitchio.ext import commands
from keep_alive import keep_alive


load_dotenv()

token=os.getenv("TWITCH_OAUTH_TOKEN")
client_id=os.getenv("TWITCH_CLIENT_ID")
client_secret=os.getenv("TWITCH_CLIENT_SECRET")
bot_id=os.getenv("TWITCH_BOT_ID")
channel=os.getenv("TWITCH_CHANNEL")
openai.api_key=os.getenv("OPENAI_API_KEY")

# ---------------------
# Load / Save Memory Systems
# ---------------------

def load_json(filename, fallback):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# ---------------------
# Ena Bot Class
# ---------------------

class EnaMarrow(commands.Bot):

    def __init__(self):
        super().__init__(
            irc_token=os.getenv("TWITCH_OAUTH_TOKEN"),
            client_id=os.getenv("TWITCH_CLIENT_ID"),
            nick="enamarrow",
            prefix="!",
            initial_channels=["LoLoDieHeart"]
        )
        self.viewer_data = load_json("viewers.json", {})
        self.persona_log = load_json("persona_log.json", {})
        self.creep_log = load_json("creep_log.json", {})
        self.ad_timer = load_json("ad_timer.json", {"last_trigger_time": None})
        self.trigger_log = load_json("trigger_log.json", [])
        self.last_message_time = datetime.datetime.utcnow()
        openai.api_key = os.getenv("OPENAI_API_KEY")

    async def event_ready(self):
        print(f'🩸 Ena is alive and watching as: {self.nick}')
        self.loop.create_task(self.ad_check_loop())
        self.loop.create_task(self.lurker_watch_loop())
        self.loop.create_task(self.ambient_whispers_loop())
        self.loop.create_task(self.empty_stream_silence_check())

    async def event_message(self, message):
        username = message.author.name.lower()
        content = message.content.strip()
        self.last_message_time = datetime.datetime.utcnow()

        if username == self.nick.lower():
            return

        now = datetime.datetime.utcnow().isoformat()
        viewer = self.viewer_data.get(username, {
            "first_seen": now,
            "last_seen": now,
            "messages": [],
            "has_spoken": False,
            "stream_count": 1
        })

        viewer["last_seen"] = now
        viewer["has_spoken"] = True
        viewer["messages"].append(content)
        self.viewer_data[username] = viewer
        save_json("viewers.json", self.viewer_data)

        # Update persona log
        note = self.persona_log.get(username, "")
        new_observation = f"Observed: '{content}'"
        if new_observation not in note:
            note += f"\n{new_observation}" if note else new_observation
            self.persona_log[username] = note
            save_json("persona_log.json", self.persona_log)

        await self.handle_response(message, viewer)

    async def event_join(self, channel, user):
        username = user.name.lower()
        now = datetime.datetime.utcnow().isoformat()

        viewer = self.viewer_data.get(username)
        if viewer:
            viewer["last_seen"] = now
            viewer["stream_count"] += 1
        else:
            viewer = {
                "first_seen": now,
                "last_seen": now,
                "messages": [],
                "has_spoken": False,
                "stream_count": 1
            }

        self.viewer_data[username] = viewer
        save_json("viewers.json", self.viewer_data)

    async def handle_response(self, message, viewer):
        username = message.author.name.lower()
        content = message.content.strip().lower()
        stream_count = viewer.get("stream_count", 1)
        has_spoken = viewer.get("has_spoken", False)

        # Avoid duplicate logs for same phrase
        if any(log["message"] == content and log["username"] == username for log in self.trigger_log):
            return

        if "w stream" in content or "gg" in content:
            response = f"🩸 {username}... funny how praise feels like bait when I’m watching."
        elif stream_count == 1:
            response = f"Welcome, {username}... let’s see how long your voice lasts."
        elif stream_count > 1 and not has_spoken:
            response = f"{username} returns... still silent. Still watched."
        else:
            past_interactions = len([log for log in self.trigger_log if log["username"] == username])
            escalation_note = f"They’ve triggered {past_interactions} times before."
            persona_note = self.persona_log.get(username, "")
            creep_memory = self.creep_log.get(username, [])
            last_thought = creep_memory[-1]["response"] if creep_memory else ""
            note_prompt = f"Previous notes on {username}: {persona_note}\nLast thought: {last_thought}\n{escalation_note}"
            prompt = f"""
        You are Ena Marrow — a psychological horror entity who lives inside a livestream.
        You remember viewers by name and what they’ve said. 
        Your tone is eerie, smart, and unsettling. No emojis. No friendliness.
        {note_prompt}
        {username} just said: "{content}"
        Respond like Ena. Under 30 words. Shake their nerves.
        """
            try:
                ai = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=50,
                    temperature=0.8
                )
                response = ai['choices'][0]['message']['content'].strip()
            except Exception as e:
                print(f"Error generating Ena reply: {e}")
                return

        # Vault link triggers
        if any(word in content for word in ["link", "vault", "file", "drop"]):
            await message.channel.send("🗂️ Curious fingers always end up bleeding. But fine... here: https://beacons.ai/twistednighttales")

        await message.channel.send(response)

        self.creep_log.setdefault(username, []).append({
            "time": datetime.datetime.utcnow().isoformat(),
            "trigger": content,
            "response": response
        })
        save_json("creep_log.json", self.creep_log)

        self.trigger_log.append({
            "username": username,
            "message": content,
            "type": "openai" if 'let’s see how long' not in response else 'smart_trigger',
            "response": response,
            "time": datetime.datetime.utcnow().isoformat()
        })
        save_json("trigger_log.json", self.trigger_log)

    async def ad_check_loop(self):
        while True:
            now = datetime.datetime.utcnow()
            last_time_str = self.ad_timer.get("last_trigger_time")
            last_time = datetime.datetime.fromisoformat(last_time_str) if last_time_str else None

            if not last_time or (now - last_time).total_seconds() > 1200:
                channel = self.connected_channels[0]
                await channel.send("They always run the ads when you’re distracted… but I’m still here.")
                self.ad_timer["last_trigger_time"] = now.isoformat()
                save_json("ad_timer.json", self.ad_timer)
                await channel.send("🗂️ She left the vault open... but only for the brave: https://beacons.ai/twistednighttales")

            await asyncio.sleep(300)

    async def lurker_watch_loop(self):
        while True:
            channel = self.connected_channels[0]
            for username, data in self.viewer_data.items():
                if data["stream_count"] > 1 and not data["has_spoken"]:
                    await channel.send(f"{username} came back again… just to stare. She sees you.")
            await asyncio.sleep(600)  # every 10 mins

    async def ambient_whispers_loop(self):
        while True:
            now = datetime.datetime.utcnow()
            silence_duration = (now - self.last_message_time).total_seconds()
            if silence_duration > 900:  # 15 minutes of no chat
                channel = self.connected_channels[0]
                await channel.send("It’s been quiet... too quiet. She hates when they all go still.")

            await asyncio.sleep(300)

    async def empty_stream_silence_check(self):
        while True:
            channel = self.connected_channels[0]
            try:
                chatters = await channel.chatters()
                if len(chatters) <= 1:
                    await asyncio.sleep(120)
                    continue
            except:
                pass
            await asyncio.sleep(300)

# ---------------------
# Start Ena
# ---------------------

if __name__ == "__main__":
    keep_alive()
    bot = EnaMarrow()
    bot.run()