import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict
import random
import paho.mqtt.client as mqtt

# Thème Nord
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
TOPICS = {
    "question": "quiz/question",
    "reponse": "quiz/reponse",
    "presence": "quiz/presence",
    "score": "quiz/score/",
    "feedback": "quiz/feedback/"
}

# Charger toutes les questions
with open("questions.json", "r", encoding="utf-8") as f:
    all_questions = json.load(f)

class CustomTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview.Heading", font=("Arial", 12, "bold"), background=NORD["header"], foreground=NORD["accent"])
        style.configure("Treeview", rowheight=28, font=("Arial", 11), background=NORD["bg"], fieldbackground=NORD["bg"], foreground=NORD["fg"])

class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        canvas = tk.Canvas(self, bg=NORD["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=NORD["bg"])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all"),
                width=e.width  # Force le canvas à prendre la même largeur que le contenu (centrage)
            )
        )

        window = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="n")

        def resize_canvas(event):
            canvas.itemconfig(window, width=event.width)

        canvas.bind("<Configure>", resize_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Scroll molette
        self.scrollable_frame.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)), "units")))
        self.scrollable_frame.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))



class GestionnaireQuiz:
    def __init__(self, root):
        self.root = root
        self.clients = set()
        self.client_scores = defaultdict(int)
        self.answers_received = defaultdict(list)
        self.nicknames = {}
        self.started = False
        self.current_question_index = 0
        self.nb_questions = tk.IntVar(value=5)
        self.custom_questions = []
        self.mode_selection = tk.StringVar(value="Classiques")
        self.timer_duration = tk.IntVar(value=15)

        self.setup_ui()
        self.setup_mqtt()

    def setup_ui(self):
        self.root.title("🎓 Gestionnaire Quiz")
        self.root.geometry("850x650")
        self.root.configure(bg=NORD["bg"])

        header = tk.Frame(self.root, bg=NORD["header"], height=50)
        header.pack(fill="x")
        tk.Label(header, text="Gestionnaire Quiz", font=("Arial", 18, "bold"), bg=NORD["header"], fg=NORD["accent"]).pack(side="left", padx=10)
        self.lbl_connected = tk.Label(header, text="0 joueurs connectés", font=("Arial", 12), bg=NORD["header"], fg=NORD["fg"])
        self.lbl_connected.pack(side="right", padx=10)

        ctrl = tk.Frame(self.root, bg=NORD["bg"], pady=10)
        ctrl.pack()

        tk.Label(ctrl, text="Nombre de questions :", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        self.entry_questions = tk.Entry(ctrl, textvariable=self.nb_questions, font=("Arial", 12), width=5, justify="center")
        self.entry_questions.pack(side="left", padx=5)

        tk.Label(ctrl, text="Mode :", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        self.combo_mode = ttk.Combobox(ctrl, textvariable=self.mode_selection, values=["Classiques", "Personnalisées"], state="readonly", width=15)
        self.combo_mode.pack(side="left", padx=5)

        tk.Label(ctrl, text="Temps par question (en secondes) :", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        self.entry_timer = tk.Entry(ctrl, textvariable=self.timer_duration, font=("Arial", 12), width=5, justify="center")
        self.entry_timer.pack(side="left", padx=5)

        self.btn_start = tk.Button(ctrl, text="🚀 Lancer le Quiz", font=("Arial", 13, "bold"), bg=NORD["accent"], fg=NORD["bg"],
                                   activebackground=NORD["button_active"], relief="flat", command=self.start_quiz, cursor="hand2")
        self.btn_start.pack(side="left", padx=10)

        self.lbl_question = tk.Label(self.root, text="Prêt à démarrer...", font=("Arial", 11), bg=NORD["bg"], fg=NORD["fg"], wraplength=700, pady=20)
        self.lbl_question.pack()

        self.tree = CustomTreeview(self.root, columns=("pseudo", "score"), show="headings")
        self.tree.heading("pseudo", text="Joueur")
        self.tree.heading("score", text="Score")
        self.tree.column("pseudo", width=420)
        self.tree.column("score", width=200, anchor="center")
        self.tree.pack(pady=10, padx=20, fill="both", expand=True)

        # --- Partie création de question centrée et organisée ---
        separator = tk.Label(self.root, text="Créer une nouvelle question :", font=("Arial", 14, "bold"), bg=NORD["bg"], fg=NORD["accent"])
        separator.pack(pady=10)

        scroll_frame = ScrollableFrame(self.root, height=300)
        scroll_frame.pack(fill="x", padx=10, pady=5)

        create_frame = scroll_frame.scrollable_frame


        # Question centrée
        question_frame = tk.Frame(create_frame, bg=NORD["bg"])
        question_frame.pack(pady=5)
        tk.Label(question_frame, text="Question :", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        self.entry_new_question = tk.Entry(question_frame, font=("Arial", 12), width=60)
        self.entry_new_question.pack(side="left", padx=5)

        # Choix centrés et organisés (2 au départ)
        self.choices_frame = tk.Frame(create_frame, bg=NORD["bg"])
        self.choices_frame.pack(pady=5)
        self.entries_choices = []
        self.max_choices = 6
        self.init_choices(2)

        # Bouton pour ajouter un choix
        self.btn_add_choice = tk.Button(create_frame, text="Ajouter un choix", font=("Arial", 11),
                                        bg=NORD["button"], fg=NORD["fg"], activebackground=NORD["button_active"],
                                        command=self.add_choice, cursor="hand2")
        self.btn_add_choice.pack(pady=3)

        # Bonne réponse centrée
        answer_frame = tk.Frame(create_frame, bg=NORD["bg"])
        answer_frame.pack(pady=5)
        self.correct_choice = tk.IntVar(value=0)
        tk.Label(answer_frame, text="Index bonne réponse (0,1...)", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        self.entry_correct = tk.Entry(answer_frame, textvariable=self.correct_choice, font=("Arial", 12), width=5)
        self.entry_correct.pack(side="left", padx=5)

        # Bouton ajouter question centré
        self.btn_add_question = tk.Button(create_frame, text="➕ Envoyer Question", font=("Arial", 13), bg=NORD["accent"], fg=NORD["bg"],
                                          activebackground=NORD["button_active"], relief="flat", command=self.add_custom_question, cursor="hand2")
        self.btn_add_question.pack(pady=10)

    def init_choices(self, n):
        # Efface les anciens champs
        for widget in self.choices_frame.winfo_children():
            widget.destroy()
        self.entries_choices.clear()
        for i in range(n):
            self.add_choice(init=True)

    def add_choice(self, init=False):
        if len(self.entries_choices) >= self.max_choices:
            messagebox.showinfo("Limite", f"Tu ne peux pas avoir plus de {self.max_choices} choix.")
            return
        idx = len(self.entries_choices)
        row_frame = tk.Frame(self.choices_frame, bg=NORD["bg"])
        row_frame.pack(anchor="center", pady=2)
        tk.Label(row_frame, text=f"Choix {idx+1} :", font=("Arial", 12), bg=NORD["bg"], fg=NORD["fg"]).pack(side="left", padx=5)
        entry = tk.Entry(row_frame, font=("Arial", 12), width=45)
        entry.pack(side="left", padx=5)
        self.entries_choices.append(entry)

    def setup_mqtt(self):
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def on_connect(self, client, userdata, flags, rc):
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
            print(f"Erreur MQTT : {e}")

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
            if not any(x[0] == cid for x in self.answers_received[qid]):
                self.answers_received[qid].append((cid, answer))
                self.update_scoreboard(live_update=True)

    def update_ui(self):
        self.lbl_connected.config(text=f"{len(self.clients)} joueurs connectés")
        self.update_scoreboard()

    def update_scoreboard(self, live_update=False):
        for item in self.tree.get_children():
            self.tree.delete(item)

        all_scores = [(cid, self.client_scores.get(cid, 0)) for cid in self.clients]
        sorted_scores = sorted(all_scores, key=lambda x: (-x[1], self.nicknames.get(x[0], "")))

        last_score = None
        last_rank = 0
        actual_rank = 1

        leaderboard = []  # Liste pour envoyer le classement

        for i, (cid, score) in enumerate(sorted_scores):
            if score == last_score:
                rank = last_rank
            else:
                rank = i + 1  # 👈 Le rang devient l’index+1 (compétitif)

            last_score = score
            last_rank = rank

            pseudo = self.nicknames.get(cid, cid)
            if rank == 1:
                pseudo = f"🏆 {pseudo}"
            elif rank == 2:
                pseudo = f"🥈 {pseudo}"
            elif rank == 3:
                pseudo = f"🥉 {pseudo}"

            leaderboard.append({
                "rank": rank,
                "pseudo": pseudo,
                "score": score
            })

            self.tree.insert("", "end", values=(pseudo, f"{score}"))

        # Publier le classement sur un topic MQTT
        self.client.publish("quiz/classement", json.dumps(leaderboard))

    def add_custom_question(self):
        nb_max = self.nb_questions.get()
        if len(self.custom_questions) >= nb_max:
            messagebox.showwarning(
                "Limite atteinte",
                f"Tu as déjà créé {nb_max} questions personnalisées.\n"
                "Augmente le nombre de questions si tu veux en ajouter d'autres."
            )
            return

        qtext = self.entry_new_question.get().strip()
        choices = [entry.get().strip() for entry in self.entries_choices if entry.get().strip()]
        correct = self.correct_choice.get()

        if not qtext or len(choices) < 2 or correct >= len(choices) or correct < 0:
            messagebox.showerror("Erreur", "Il faut au moins 2 choix, et l'index de la bonne réponse doit être correct.")
            return

        question = {
            "question": qtext,
            "options": choices,
            "answer": correct
        }
        self.custom_questions.append(question)
        messagebox.showinfo("✅", f"Question ajoutée ({len(self.custom_questions)}/{nb_max}) !")
        self.entry_new_question.delete(0, tk.END)
        for entry in self.entries_choices:
            entry.delete(0, tk.END)
        self.correct_choice.set(0)
        self.init_choices(2)


    def start_quiz(self):
        if not self.clients:
            messagebox.showwarning("Avertissement", "Aucun joueur connecté.")
            return

        mode = self.mode_selection.get()
        nb = self.nb_questions.get()
        timer = self.timer_duration.get()

        if timer <= 4 or timer > 61:
            messagebox.showerror("Erreur", "Le temps doit être compris entre 5 et 60 secondes.")
            return

        questions = []

        if mode == "Classiques":
            if len(all_questions) < nb:
                messagebox.showerror("Erreur", "Pas assez de questions classiques.")
                return
            questions = random.sample(all_questions, nb)
        elif mode == "Personnalisées":
            if len(self.custom_questions) < nb:
                messagebox.showerror("Erreur", "Pas assez de questions personnalisées.")
                return
            questions = random.sample(self.custom_questions, nb)

        self.questions = questions
        self.btn_start.config(state="disabled")
        self.started = True
        threading.Thread(target=self.run_quiz, daemon=True).start()

    def run_quiz(self):
        for index, question in enumerate(self.questions):
            self.current_question_index = index
            self.lbl_question.config(text=f"Question {index+1}/{len(self.questions)}\n\n{question['question']}")
            self.answers_received[index] = []
            self.client.publish(TOPICS["question"], json.dumps({
                "id": index,
                "question": question["question"],
                "options": question["options"],
                "timer": self.timer_duration.get()
            }))
            time.sleep(self.timer_duration.get() + 2)
            correct_index = question["answer"]
            for client_id, answer_index in self.answers_received[index]:
                correct = (answer_index == correct_index)
                if correct:
                    self.client_scores[client_id] += 1
                self.client.publish(f"{TOPICS['feedback']}{client_id}", json.dumps({
                    "answer_index": answer_index,
                    "correct": correct,
                    "correct_answer": correct_index
                }))
            self.update_scoreboard()
            time.sleep(2)
        self.finish_quiz()


    def finish_quiz(self):
        all_scores = [(cid, self.client_scores.get(cid, 0)) for cid in self.clients]
        sorted_scores = sorted(all_scores, key=lambda x: (-x[1], self.nicknames.get(x[0], "")))

        # Générer le classement avec gestion des égalités
        classement = []
        last_score = None
        last_rank = 0
        actual_rank = 1

        for i, (cid, score) in enumerate(sorted_scores):
            if score == last_score:
                rank = last_rank
            else:
                rank = i + 1  # 👈 Correction ici aussi

            last_score = score
            last_rank = rank

            classement.append({
                "client_id": cid,
                "nickname": self.nicknames.get(cid, cid),
                "score": score,
                "rank": rank
            })


        # ✅ Publier le classement final aux clients pour qu’ils affichent leur résultat
        self.client.publish("quiz/fin", json.dumps({"classement": classement}))

        # ✅ Afficher côté gestionnaire
        winners = classement[:3]
        message = "🏅 Résultats du Quiz 🏅\n\n"
        for player in winners:
            message += f"{player['rank']}. {player['nickname']} - {player['score']} pts\n"

        messagebox.showinfo("Classement Final", message)


if __name__ == "__main__":
    root = tk.Tk()
    app = GestionnaireQuiz(root)
    root.mainloop()
