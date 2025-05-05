import tkinter as tk
import uuid
import json
import paho.mqtt.client as mqtt
import threading

# Thème Nord foncé
NORD = {
    "bg": "#2E3440",
    "fg": "#ECEFF4",
    "accent": "#88C0D0",
    "button": "#4C566A",
    "button_active": "#5E81AC",
    "success": "#A3BE8C",
    "error": "#BF616A",
    "warning": "#EBCB8B",
    "header": "#3B4252"
}

BROKER = "broker.hivemq.com"
PORT = 1883

class ClientQuiz:
    def __init__(self, master):
        self.master = master
        self.master.title("🎮 Client Quiz")
        self.master.geometry("520x600")
        self.master.configure(bg=NORD["bg"])

        self.client_id = str(uuid.uuid4())[:8]
        self.nickname = ""
        self.timer_id = None
        self.timer_running = False
        self.has_answered = False

        self.get_nickname()

        tk.Label(master, text="Quiz en ligne", font=("Arial", 18, "bold"),
                 bg=NORD["header"], fg=NORD["accent"]).pack(fill="x", pady=(10, 0))

        self.label_question = tk.Label(master, text="", font=("Arial", 16, "bold"),
                                       wraplength=480, bg=NORD["bg"], fg=NORD["fg"], justify="center")
        self.label_question.pack(pady=20)

        self.buttons = []
        for i in range(4):
            btn = tk.Button(master, text="", font=("Arial", 13, "bold"), width=40, height=2,
                            command=lambda idx=i: self.send_answer(idx),
                            bg=NORD["button"], fg=NORD["accent"],
                            activebackground=NORD["button_active"], activeforeground=NORD["fg"],
                            relief="ridge", bd=2, cursor="hand2")
            btn.pack(pady=7)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=NORD["button_active"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=NORD["button"]))
            self.buttons.append(btn)

        self.timer_label = tk.Label(master, text="", font=("Arial", 14, "bold"),
                                    bg=NORD["bg"], fg=NORD["warning"])
        self.timer_label.pack(pady=10)

        self.result_label = tk.Label(master, text="", font=("Arial", 14, "bold"),
                                     bg=NORD["bg"], fg=NORD["fg"])
        self.result_label.pack(pady=10)

        self.current_question = None
        self.time_left = 0

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT)

        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def get_nickname(self):
        def submit():
            name = entry.get()
            if name.strip():
                self.nickname = name.strip()
                popup.destroy()
            else:
                error_label.config(text="Entrez un pseudo !", fg=NORD["error"])

        popup = tk.Toplevel(self.master)
        popup.title("Votre pseudo")
        popup.geometry("320x180")
        popup.configure(bg=NORD["bg"])
        popup.grab_set()

        tk.Label(popup, text="Entrez votre pseudo :", bg=NORD["bg"], fg=NORD["fg"], font=("Arial", 13)).pack(pady=10)
        entry = tk.Entry(popup, font=("Arial", 13), bg=NORD["button"], fg=NORD["fg"], insertbackground=NORD["fg"])
        entry.pack(pady=5)
        error_label = tk.Label(popup, text="", bg=NORD["bg"], fg=NORD["error"], font=("Arial", 11))
        error_label.pack(pady=5)
        tk.Button(popup, text="Valider", command=submit, bg=NORD["button_active"], fg=NORD["fg"],
                  font=("Arial", 12), relief="flat", cursor="hand2").pack(pady=10)

        self.master.wait_window(popup)

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe("quiz/question")
        client.subscribe(f"quiz/feedback/{self.client_id}")
        client.subscribe(f"quiz/score/{self.client_id}")

        presence = {"id": self.client_id, "nickname": self.nickname}
        client.publish("quiz/presence", json.dumps(presence))

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        data = json.loads(msg.payload.decode())
        if topic == "quiz/question":
            self.master.after(0, self.display_question, data)
        elif topic == f"quiz/feedback/{self.client_id}":
            self.master.after(0, self.display_feedback, data)
        elif topic == f"quiz/score/{self.client_id}":
            self.master.after(0, self.display_final_score, data)

    def display_question(self, data):
        self.stop_timer()
        self.current_question = data
        self.has_answered = False
        question_text = data.get("question", "Question non trouvée.")
        options = data.get("options", [])

        self.label_question.config(text=question_text)
        self.result_label.config(text="")

        for i, btn in enumerate(self.buttons):
            if i < len(options):
                btn.config(text=options[i], state="normal", bg=NORD["button"], fg=NORD["accent"])
            else:
                btn.config(text="", state="disabled", bg=NORD["bg"])

        self.time_left = data.get("timer", 10)
        self.timer_running = True
        self.update_timer()

    def update_timer(self):
        if not self.timer_running:
            return
        if self.time_left >= 0:
            color = NORD["error"] if self.time_left <= 5 else NORD["warning"]
            self.timer_label.config(text=f"⏳ Temps restant : {self.time_left}s", fg=color)
            self.time_left -= 1
            self.timer_id = self.master.after(1000, self.update_timer)
        else:
            self.timer_label.config(text="⏰ Temps écoulé !", fg=NORD["error"])
            for btn in self.buttons:
                btn.config(state="disabled")
            self.timer_running = False

            # ➡️ Si pas répondu, on envoie une réponse automatique (-1)
            if not self.has_answered and self.current_question:
                self.send_answer(-1)

    def stop_timer(self):
        self.timer_running = False
        if self.timer_id is not None:
            self.master.after_cancel(self.timer_id)
            self.timer_id = None

    def send_answer(self, index):
        if not self.current_question or self.has_answered:
            return
        self.has_answered = True
        for btn in self.buttons:
            btn.config(state="disabled")
        answer = {
            "question_id": self.current_question.get("id"),
            "answer_index": index,
            "client_id": self.client_id
        }
        self.client.publish("quiz/reponse", json.dumps(answer))

    def display_feedback(self, data):
        correct = data.get("correct", False)
        correct_index = data.get("correct_answer")
        if correct_index is None:
            correct_index = data.get("correct_answer_index")

        if correct:
            self.result_label.config(text="✅ Bonne réponse !", fg=NORD["success"])
        else:
            if self.current_question and "options" in self.current_question and correct_index is not None:
                try:
                    right_answer = self.current_question["options"][correct_index]
                    self.result_label.config(text=f"❌ Mauvaise réponse\nBonne : {right_answer}", fg=NORD["error"])
                except Exception:
                    self.result_label.config(text="❌ Mauvaise réponse", fg=NORD["error"])
            else:
                self.result_label.config(text="❌ Mauvaise réponse", fg=NORD["error"])

    def display_final_score(self, data):
        self.stop_timer()
        score = data.get("score", 0)
        total = data.get("total", 0)
        rank = data.get("rank", 0)
        players = data.get("total_players", 0)

        self.label_question.config(text="🎉 Quiz terminé !")
        self.result_label.config(
            text=f"🏆 Score : {score}/{total}\nClassement : {rank}/{players}",
            fg=NORD["success"]
        )
        for btn in self.buttons:
            btn.config(text="", state="disabled", bg=NORD["bg"])

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientQuiz(root)
    root.mainloop()
