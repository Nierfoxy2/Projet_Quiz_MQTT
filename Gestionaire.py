import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict
import paho.mqtt.client as mqtt

# Configuration MQTT
BROKER = "broker.hivemq.com"
PORT = 1883
TOPICS = {
    "question": "quiz/question",
    "reponse": "quiz/reponse",
    "presence": "quiz/presence",
    "score": "quiz/score/",
    "feedback": "quiz/feedback/"
}

# Chargement des questions
with open("/Users/mac/Desktop/Projet/questions.json", "r", encoding="utf-8") as f:
    questions = json.load(f)

class CustomTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Arial", 12, "bold"))
        style.configure("Treeview", rowheight=28, font=("Arial", 11))

class GestionnaireQuiz:
    def __init__(self, root):
        self.root = root
        self.clients = set()
        self.client_scores = defaultdict(int)
        self.answers_received = defaultdict(list)
        self.nicknames = {}
        self.started = False
        self.current_question_index = 0

        self.setup_ui()
        self.setup_mqtt()

    def setup_ui(self):
        self.root.title("🎓 Gestionnaire Quiz")
        self.root.geometry("800x600")
        self.root.configure(bg="#f4f4f4")

        # En-tête
        header = tk.Frame(self.root, bg="#3F51B5", height=50)
        header.pack(fill="x")
        tk.Label(header, text="Gestionnaire Quiz", font=("Arial", 16, "bold"), bg="#3F51B5", fg="white").pack(side="left", padx=10)
        self.lbl_connected = tk.Label(header, text="0 joueurs connectés", font=("Arial", 12), bg="#3F51B5", fg="white")
        self.lbl_connected.pack(side="right", padx=10)

        # Contrôle
        ctrl = tk.Frame(self.root, bg="#f4f4f4", pady=10)
        ctrl.pack()
        self.btn_start = tk.Button(ctrl, text="🚀 Lancer le Quiz", font=("Arial", 12, "bold"), bg="#4CAF50", fg="white",
                                   activebackground="#388E3C", command=self.start_quiz)
        self.btn_start.pack()

        # Question affichée
        self.lbl_question = tk.Label(self.root, text="Prêt à démarrer...", font=("Arial", 14), bg="#f4f4f4", wraplength=700, pady=20)
        self.lbl_question.pack()

        # Tableau des scores
        self.tree = CustomTreeview(self.root, columns=("pseudo", "score"), show="headings")
        self.tree.heading("pseudo", text="Joueur")
        self.tree.heading("score", text="Score")
        self.tree.column("pseudo", width=400)
        self.tree.column("score", width=200, anchor="center")
        self.tree.pack(pady=10, padx=20, fill="both", expand=True)

    def setup_mqtt(self):
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(TOPICS["presence"])
        client.subscribe(TOPICS["reponse"])

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            if msg.topic == TOPICS["presence"]:
                self.handle_presence(data)
            elif msg.topic == TOPICS["reponse"] and self.started:
                self.handle_answer(data)
        except Exception as e:
            print(f"Erreur de message MQTT : {e}")

    def handle_presence(self, data):
        client_id = data.get("id")
        nickname = data.get("nickname", "").strip()
        if not client_id:
            return
        if not nickname:
            nickname = f"Joueur-{client_id[:4]}"
        if client_id not in self.clients:
            self.clients.add(client_id)
            self.nicknames[client_id] = nickname
            self.update_ui()

    def handle_answer(self, data):
        qid = data.get("question_id")
        answer = data.get("answer_index")
        cid = data.get("client_id")
        if cid in self.clients and qid == self.current_question_index:
            self.answers_received[qid].append((cid, answer))

    def update_ui(self):
        self.lbl_connected.config(text=f"{len(self.clients)} joueurs connectés")
        self.update_scoreboard()

    def update_scoreboard(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        sorted_scores = sorted(self.client_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (cid, score) in enumerate(sorted_scores, start=1):
            self.tree.insert("", "end", values=(f"{i}. {self.nicknames.get(cid, cid)}", f"{score}"))

    def start_quiz(self):
        if not self.clients:
            messagebox.showwarning("Avertissement", "Aucun joueur connecté.")
            return
        self.btn_start.config(state="disabled")
        self.started = True
        threading.Thread(target=self.run_quiz, daemon=True).start()

    def run_quiz(self):
        for index, question in enumerate(questions):
            self.current_question_index = index
            self.lbl_question.config(text=f"Question {index+1}/{len(questions)}\n\n{question['question']}")
            self.answers_received[index] = []

            self.client.publish(TOPICS["question"], json.dumps({
                "id": index,
                "question": question["question"],
                "options": question["options"],
                "timer": 15
            }))

            time.sleep(17)

            correct_index = question["answer"]
            for client_id, answer_index in self.answers_received[index]:
                correct = (answer_index == correct_index)
                if correct:
                    self.client_scores[client_id] += 1
                self.client.publish(f"{TOPICS['feedback']}{client_id}", json.dumps({
                    "answer_index": answer_index,
                    "correct": correct,
                    "correct_answer_index": correct_index
                }))
            self.update_scoreboard()
            time.sleep(3)

        self.finish_quiz()

    def finish_quiz(self):
        total = len(questions)
        sorted_scores = sorted(self.client_scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (cid, score) in enumerate(sorted_scores, 1):
            self.client.publish(f"{TOPICS['score']}{cid}", json.dumps({
                "score": score,
                "rank": rank,
                "total": total,
                "total_players": len(sorted_scores)
            }))
        self.lbl_question.config(text="🎉 Quiz terminé !", fg="green")
        self.btn_start.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = GestionnaireQuiz(root)
    root.mainloop()
