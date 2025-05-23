import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PollHandler
import spacy
import random
from config import TOKEN
import json
import logging
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load spaCy model for English (since the input may be multilingual, we'll focus on English translation or key entities)
nlp = spacy.load("en_core_web_sm")

class QuizBot:
    def __init__(self):
        self.quizzes = []
        self.current_quiz = None
        self.user_data = {}

    def extract_quiz_data(self, text):
        """Generate quizzes from unstructured current affairs text."""
        doc = nlp(text)
        quizzes = []
        
        # Extract sentences and key entities (e.g., people, organizations, locations, dates)
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]
        entities = [(ent.text, ent.label_) for ent in doc.ents]

        # Generate up to 10 quizzes based on sentences and entities
        for i, sentence in enumerate(sentences[:10]):  # Limit to 10
            # Find entities in the sentence
            sent_doc = nlp(sentence)
            sent_entities = [(ent.text, ent.label_) for ent in sent_doc.ents]
            
            # Create a question based on an entity or fact
            question = None
            correct_answer = None
            incorrect_answers = []
            
            # Strategy 1: Question about a person, place, or organization
            for entity, label in sent_entities:
                if label in ["PERSON", "GPE", "ORG", "DATE", "EVENT"]:
                    # Example: "Who inaugurated 103 redeveloped railway stations?"
                    if label == "PERSON" and "inaugurat" in sentence.lower():
                        question = f"Who inaugurated the event or project mentioned in the news on {entity}?"
                        correct_answer = entity
                        # Generate incorrect options (other people from text or generic names)
                        incorrect_answers = [e[0] for e in entities if e[1] == "PERSON" and e[0] != entity]
                        incorrect_answers.extend(["Rahul Gandhi", "Amit Shah", "Sonia Gandhi"][:3-len(incorrect_answers)])
                        break
                    elif label == "GPE" and "stadium" in sentence.lower():
                        question = f"In which city is the stadium named after a cricketer located?"
                        correct_answer = entity
                        incorrect_answers = [e[0] for e in entities if e[1] == "GPE" and e[0] != entity]
                        incorrect_answers.extend(["Delhi", "Kolkata", "Chennai"][:3-len(incorrect_answers)])
                        break
                    elif label == "ORG" and "collaborated" in sentence.lower():
                        question = f"Which organization collaborated with IIT Guwahati for an AI program?"
                        correct_answer = entity
                        incorrect_answers = [e[0] for e in entities if e[1] == "ORG" and e[0] != entity]
                        incorrect_answers.extend(["TCS", "Infosys", "Wipro"][:3-len(incorrect_answers)])
                        break

            # Strategy 2: Numeric or factual question
            if not question:
                numbers = re.findall(r'\d+\.?\d*', sentence)
                if numbers and any(keyword in sentence.lower() for keyword in ["crore", "percent", "km"]):
                    number = numbers[0]
                    if "crore" in sentence.lower():
                        question = f"What is the approximate budget of the projects inaugurated in Rajasthan?"
                        correct_answer = f"{number} crore"
                        incorrect_answers = [f"{int(number)*2} crore", f"{int(number)//2} crore", f"{int(number)+100} crore"]
                    elif "percent" in sentence.lower():
                        question = f"What is the projected GDP growth rate for India in 2025?"
                        correct_answer = f"{number}%"
                        incorrect_answers = [f"{float(number)+1}%", f"{float(number)-1}%", f"{float(number)+2}%"]

            # Ensure valid quiz
            if question and correct_answer and len(incorrect_answers) >= 3:
                answers = incorrect_answers[:3] + [correct_answer]
                random.shuffle(answers)
                correct_idx = answers.index(correct_answer)
                quizzes.append({
                    'question': question,
                    'answers': answers,
                    'correct': correct_idx
                })

        return quizzes[:10]  # Limit to 10 quizzes

    def start(self, update, context):
        update.message.reply_text("Send current affairs text, and I'll generate quizzes automatically. Use /generate to start quizzes in this chat.")

    def receive_data(self, update, context):
        text = update.message.text
        self.quizzes = self.extract_quiz_data(text)
        if self.quizzes:
            update.message.reply_text(f"Generated {len(self.quizzes)} quizzes. Use /generate to start.")
            # Save quizzes to a file
            with open('quizzes.json', 'w') as f:
                json.dump(self.quizzes, f)
        else:
            update.message.reply_text("Could not generate quizzes. Please provide more detailed current affairs text.")

    def generate_quiz(self, update, context):
        if not self.quizzes:
            update.message.reply_text("No quizzes available. Send current affairs text first.")
            return
        
        chat_id = update.message.chat_id
        self.current_quiz = 0
        self.user_data[chat_id] = {'score': 0, 'total': len(self.quizzes)}
        
        self.send_quiz(update, context, chat_id)

    def send_quiz(self, update, context, chat_id):
        if self.current_quiz >= len(self.quizzes):
            score = self.user_data[chat_id]['score']
            total = self.user_data[chat_id]['total']
            context.bot.send_message(chat_id=chat_id, text=f"Quiz finished! Your score: {score}/{total}")
            self.current_quiz = None
            return

        quiz = self.quizzes[self.current_quiz]
        try:
            message = context.bot.send_poll(
                chat_id=chat_id,
                question=quiz['question'],
                options=quiz['answers'],
                type=telegram.Poll.QUIZ,
                correct_option_id=quiz['correct'],
                is_anonymous=False,
                explanation="Refer to the current affairs text for details.",
                timeout=30
            )
            context.bot_data[message.poll.id] = chat_id
            self.current_quiz += 1
        except telegram.error.NetworkError as e:
            logger.error(f"Network error sending poll: {e}")
            context.bot.send_message(chat_id=chat_id, text="Network issue. Retrying in 10 seconds...")
            context.job_queue.run_once(lambda _: self.send_quiz(update, context, chat_id), 10)

    def handle_poll_answer(self, update, context):
        poll = update.poll
        chat_id = context.bot_data.get(poll.id)
        if not chat_id:
            return
        
        if poll.correct_option_id in [opt.id for opt in poll.options if opt.voter_count > 0]:
            self.user_data[chat_id]['score'] += 1
        
        if self.current_quiz is not None:
            self.send_quiz(update, context, chat_id)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    bot = QuizBot()

    dp.add_handler(CommandHandler("start", bot.start))
    dp.add_handler(CommandHandler("generate", bot.generate_quiz))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, bot.receive_data))
    dp.add_handler(PollHandler(bot.handle_poll_answer, pass_chat_data=True, pass_user_data=True))

    try:
        updater.start_polling(timeout=30)
        logger.info("Bot started polling")
        updater.idle()
    except telegram.error.NetworkError as e:
        logger.error(f"Failed to start polling: {e}")
        raise

if __name__ == "__main__":
    main()
