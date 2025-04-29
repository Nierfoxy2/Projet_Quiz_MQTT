import tkinter as tk
import uuid
import json
import paho.mqtt.client as mqtt
import threading

BROKER = "broker.hivemq.com"
PORT = 1883

class ClientQuiz:
    def __init__(self, master):
        self.master = master
        self.master.title("Client Quiz")
        
        self.client_id = str(uuid.uuid4())[:8]
        self.nickname = ""
        self.get_nickname()

        self.label_question = tk.Label(master, text="", font=("Arial", 14), wraplength=400)
        self.label_question.pack(pady=10)

        self.buttons = []
        for i in range(4):
            btn = tk.Button(master, text="", font=("Arial", 12), width=30, command=lambda i=i: self.send_answer(i))
            btn.pack(pady=5)
            self.buttons.append(btn)

        self.timer_label = tk.Label(master, text="", font=("Arial", 12))
        self.timer_label.pack(pady=5)

        self.result_label = tk.Label(master, text="", font=("Arial", 14))
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

        popup = tk.Toplevel(self.master)
        popup.title("Entrez votre pseudo")
        tk.Label(popup, text="Pseudo :").pack(padx=10, pady=5)
        entry = tk.Entry(popup)
        entry.pack(padx=10, pady=5)
        entry.focus()
        tk.Button(popup, text="Valider", command=submit).pack(pady=10)
        self.master.wait_window(popup)

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe("quiz/question")
        client.subscribe(f"quiz/feedback/{self.client_id}")
        client.subscribe(f"quiz/score/{self.client_id}")

        # Envoie la présence avec pseudo
        presence_data = {
            "id": self.client_id,
            "nickname": self.nickname
        }
        client.publish("quiz/presence", json.dumps(presence_data))

    def on_message(self, client, userdata, msg):
        if msg.topic == "quiz/question":
            data = json.loads(msg.payload.decode())
            self.master.after(0, self.display_question, data)
        elif msg.topic == f"quiz/feedback/{self.client_id}":
            data = json.loads(msg.payload.decode())
            self.master.after(0, self.display_feedback, data)
        elif msg.topic == f"quiz/score/{self.client_id}":
            data = json.loads(msg.payload.decode())
            self.master.after(0, self.display_final_score, data)

    def display_question(self, data):
        self.current_question = data
        self.result_label.config(text="")
        self.label_question.config(text=data["question"])
        for i in range(4):
            option = data["options"][i] if i < len(data["options"]) else ""
            self.buttons[i].config(text=option, state="normal")
        self.time_left = data.get("timer", 10)
        self.update_timer()

    def update_timer(self):
        if self.time_left > 0:
            self.timer_label.config(text=f"Temps restant : {self.time_left} s")
            self.time_left -= 1
            self.master.after(1000, self.update_timer)
        else:
            # Ne rien faire, le gestionnaire enverra feedback "non répondu"
            self.timer_label.config(text="Temps écoulé.")

    def send_answer(self, index):
        if not self.current_question:
            return
        answer_data = {
            "question_id": self.current_question["id"],
            "answer_index": index,
            "client_id": self.client_id
        }
        self.client.publish("quiz/reponse", json.dumps(answer_data))
        for btn in self.buttons:
            btn.config(state="disabled")

    def display_feedback(self, data):
        correct = data.get("correct")
        user_choice = data.get("answer_index")
        correct_choice = data.get("correct_answer_index")
        missed = data.get("missed", False)

        if missed:
            text = f"⏱️ Temps écoulé !\nBonne réponse : {self.current_question['options'][correct_choice]}"
            color = "orange"
        elif correct:
            text = "✅ Bonne réponse !"
            color = "green"
        else:
            text = f"❌ Mauvaise réponse !\nBonne réponse : {self.current_question['options'][correct_choice]}"
            color = "red"

        self.result_label.config(text=text, fg=color)

        for btn in self.buttons:
            btn.config(state="disabled")

        self.master.after(3000, self.clear_after_feedback)

    def clear_after_feedback(self):
        self.result_label.config(text="")
        self.label_question.config(text="")
        self.timer_label.config(text="")
        self.current_question = None

    def display_final_score(self, data):
        score = data["score"]
        total = data["total"]
        rank = data["rank"]
        total_players = data["total_players"]

        self.label_question.config(text="🎉 Fin du quiz !")
        self.timer_label.config(text="")
        self.result_label.config(
            text=f"Score : {score}/{total}\nClassement : {rank} sur {total_players}",
            fg="blue"
        )
        for btn in self.buttons:
            btn.config(text="", state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientQuiz(root)
    root.mainloop()
