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
        self.master.title("🎮 Client Quiz")
        self.master.geometry("500x500")
        self.master.configure(bg="#f5f5f5")

        self.client_id = str(uuid.uuid4())[:8]
        self.nickname = ""
        self.usernames = set()  # Set pour stocker les pseudos des utilisateurs connectés (simulé ici)
        self.get_nickname()

        self.label_question = tk.Label(master, text="", font=("Arial", 15, "bold"), wraplength=450, bg="#f5f5f5")
        self.label_question.pack(pady=20)

        self.buttons = []
        for i in range(4):
            btn = tk.Button(master, text="", font=("Arial", 12), width=40, height=2, command=lambda i=i: self.send_answer(i), bg="#e0e0e0")
            btn.pack(pady=5)
            self.buttons.append(btn)

        self.timer_label = tk.Label(master, text="", font=("Arial", 12, "bold"), bg="#f5f5f5", fg="#333")
        self.timer_label.pack(pady=10)

        self.result_label = tk.Label(master, text="", font=("Arial", 13), bg="#f5f5f5")
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
            if not name.strip():
                error_label.config(text="Le pseudo ne peut pas être vide", fg="red")
            elif name.strip() in self.usernames:
                error_label.config(text="Ce pseudo est déjà pris, choisissez-en un autre.", fg="red")
            else:
                self.nickname = name.strip()
                self.usernames.add(self.nickname)  # Ajouter le pseudo à la liste
                popup.destroy()

        popup = tk.Toplevel(self.master)
        popup.title("Entrez votre pseudo")
        popup.geometry("300x180")
        popup.grab_set()
        popup.configure(bg="#ffffff")

        tk.Label(popup, text="Votre pseudo :", font=("Arial", 12), bg="#ffffff").pack(pady=5)
        entry = tk.Entry(popup, font=("Arial", 12))
        entry.pack(pady=5)
        entry.focus()

        error_label = tk.Label(popup, text="", font=("Arial", 10), bg="#ffffff")
        error_label.pack(pady=5)

        tk.Button(popup, text="Valider", font=("Arial", 11), bg="#4CAF50", fg="white", command=submit).pack(pady=5)

        self.master.wait_window(popup)

    def on_connect(self, client, userdata, flags, rc):
        client.subscribe("quiz/question")
        client.subscribe(f"quiz/feedback/{self.client_id}")
        client.subscribe(f"quiz/score/{self.client_id}")

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
            self.buttons[i].config(text=option, state="normal", bg="#e0e0e0")
        self.time_left = data.get("timer", 10)
        self.update_timer()

    def update_timer(self):
        if self.time_left > 0:
            color = "#f44336" if self.time_left <= 5 else "#333"
            self.timer_label.config(text=f"⏳ Temps restant : {self.time_left} sec", fg=color)
            self.time_left -= 1
            self.master.after(1000, self.update_timer)
        else:
            self.timer_label.config(text="⏰ Temps écoulé !", fg="#f44336")
            for btn in self.buttons:
                btn.config(state="disabled")

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
        correct_choice = data.get("correct_answer")

        if correct is None:
            text = f"⏱️ Temps écoulé !\nBonne réponse : {self.current_question['options'][correct_choice]}"
            color = "orange"
        elif correct:
            text = "✅ Bonne réponse !"
            color = "green"
        else:
            text = f"❌ Mauvaise réponse !\nBonne réponse : {self.current_question['options'][correct_choice]}"
            color = "red"

        self.result_label.config(text=text, fg=color)
        self.master.after(3000, self.clear_after_feedback)

    def clear_after_feedback(self):
        self.result_label.config(text="")
        self.label_question.config(text="")
        self.timer_label.config(text="")
        for btn in self.buttons:
            btn.config(text="", state="disabled")
        self.current_question = None

    def display_final_score(self, data):
        score = data["score"]
        total = data["total"]
        rank = data["rank"]
        total_players = data["total_players"]

        self.label_question.config(text="🎉 Fin du quiz !")
        self.timer_label.config(text="")
        self.result_label.config(
            text=f"🏅 Score : {score}/{total}\n📊 Classement : {rank} sur {total_players}",
            fg="#3F51B5"
        )
        for btn in self.buttons:
            btn.config(text="", state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientQuiz(root)
    root.mainloop()
