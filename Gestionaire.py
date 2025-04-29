import json
import time
import threading
import tkinter as tk
from tkinter import ttk
from collections import defaultdict

import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC_QUESTION = "quiz/question"
TOPIC_REPONSE = "quiz/reponse"
TOPIC_PRESENCE = "quiz/presence"
TOPIC_SCORE_BASE = "quiz/score/"

with open("questions.json", "r", encoding="utf-8") as f:
    questions = json.load(f)

class GestionnaireQuiz:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestionnaire Quiz")

        self.clients = set()
        self.client_scores = defaultdict(int)
        self.answers_received = defaultdict(list)
        self.question_index = 0
        self.started = False

        self.label_connected = tk.Label(root, text="Joueurs connectés : 0", font=("Arial", 14))
        self.label_connected.pack(pady=10)

        self.btn_start = tk.Button(root, text="Lancer la partie", font=("Arial", 14), command=self.start_quiz)
        self.btn_start.pack(pady=10)

        self.label_question = tk.Label(root, text="", font=("Arial", 16), wraplength=500)
        self.label_question.pack(pady=10)

        self.tree = ttk.Treeview(root, columns=("name", "score"), show="headings")
        self.tree.heading("name", text="Joueur")
        self.tree.heading("score", text="Score")
        self.tree.pack(pady=10)

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

        self.nicknames = {}  # id → pseudo


    def on_connect(self, client, userdata, flags, rc):
        client.subscribe(TOPIC_PRESENCE)
        client.subscribe(TOPIC_REPONSE)

    def on_message(self, client, userdata, msg):
        if msg.topic == TOPIC_PRESENCE:
            data = json.loads(msg.payload.decode())
            client_id = data["id"]
            nickname = data.get("nickname", client_id)
            if client_id not in self.clients:
                self.clients.add(client_id)
                self.nicknames[client_id] = nickname
                self.client_scores[client_id] = 0  # Nouveau : init score
                self.update_connected_label()
                self.update_score_table()          # Nouveau : afficher score dès co


        elif msg.topic == TOPIC_REPONSE and self.started:
            try:
                data = json.loads(msg.payload.decode())
                q_id = data["question_id"]
                answer = data["answer_index"]
                client_id = data["client_id"]
                self.answers_received[q_id].append((client_id, answer))
            except Exception as e:
                print(f"Erreur de réponse : {e}")

    def update_connected_label(self):
        self.label_connected.config(text=f"Joueurs connectés : {len(self.clients)}")

    def update_score_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for cid in sorted(self.client_scores.keys()):
            name = self.nicknames.get(cid, cid)
            score = self.client_scores[cid]
            self.tree.insert("", "end", values=(name, score))



    def start_quiz(self):
        if self.started or not self.clients:
            return
        self.started = True
        self.btn_start.config(state="disabled")
        threading.Thread(target=self.run_quiz, daemon=True).start()

    def run_quiz(self):
        for index, q in enumerate(questions):
            self.question_index = index
            self.answers_received[index].clear()
            question_data = {
                "id": index,
                "question": q["question"],
                "options": q["options"],
                "timer": 10
            }
            self.label_question.config(text=f"Q{index + 1}: {q['question']}")
            self.client.publish(TOPIC_QUESTION, json.dumps(question_data))

            time.sleep(12)  # délai de réponse

            correct_answer = q["answer"]
            for client_id, answer in self.answers_received[index]:
                correct = (answer == correct_answer)
                if correct:
                    self.client_scores[client_id] += 1
                feedback = {
                    "correct": correct,
                    "answer_index": answer,
                    "correct_answer_index": correct_answer
                }
                self.client.publish(f"quiz/feedback/{client_id}", json.dumps(feedback))

            self.update_score_table()
            time.sleep(5)

        self.send_final_scores()

    def send_final_scores(self):
        sorted_clients = sorted(self.client_scores.items(), key=lambda x: x[1], reverse=True)
        rankings = {cid: i + 1 for i, (cid, _) in enumerate(sorted_clients)}
        for cid in self.client_scores:
            score = self.client_scores[cid]
            rank = rankings[cid]
            final_data = {
                "score": score,
                "total": len(questions),
                "rank": rank,
                "total_players": len(self.client_scores)
            }
            self.client.publish(TOPIC_SCORE_BASE + cid, json.dumps(final_data))
        self.label_question.config(text="✅ Quiz terminé.")

if __name__ == "__main__":
    root = tk.Tk()
    app = GestionnaireQuiz(root)
    root.mainloop()
