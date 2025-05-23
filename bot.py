import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PollHandler, JobQueue
import spacy
import random
from config import TOKEN
import json
import logging
import re

# Configure detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load spaCy model with error handling
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("Successfully loaded spaCy en_core_web_sm model")
except OSError as e:
    logger.error(f"Failed to load spaCy model: {e}")
    nlp = None

class QuizBot:
    def __init__(self):
        self.quizzes = []
        self.current_quiz = None
        self.user_data = {}

    def extract_quiz_data(self, text):
        """Generate quizzes from unstructured current affairs text with deep analysis."""
        logger.debug(f"Processing input text: {text[:1000]}...")
        quizzes = []

        if not nlp:
            logger.warning("spaCy model unavailable. Using fallback method.")
            return self.fallback_quiz_extraction(text)

        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]
        entities = [(ent.text, ent.label_) for ent in doc.ents]
        logger.debug(f"Extracted {len(sentences)} sentences and {len(entities)} entities")

        for i, sentence in enumerate(sentences[:10]):
            sent_doc = nlp(sentence)
            sent_entities = [(ent.text, ent.label_) for ent in sent_doc.ents]
            logger.debug(f"Sentence {i+1}: {sentence}")
            logger.debug(f"Entities in sentence: {sent_entities}")

            question = None
            correct_answer = None
            incorrect_answers = []

            for entity, label in sent_entities:
                entity_lower = entity.lower()
                sentence_lower = sentence.lower()
                if label in ["PERSON", "GPE", "ORG", "DATE", "EVENT"]:
                    if label == "PERSON" and any(k in sentence_lower for k in ["inaugurat", "launch", "open"]):
                        question = f"Who inaugurated the event or project mentioned on {entity}?"
                        correct_answer = entity
                        incorrect_answers = [e[0] for e in entities if e[1] == "PERSON" and e[0] != entity]
                        incorrect_answers.extend(["Rahul Gandhi", "Amit Shah", "Sonia Gandhi"][:3-len(incorrect_answers)])
                        logger.debug(f"Generated person-based question: {question}")
                        break
                    elif label == "GPE" and any(k in sentence_lower for k in ["stadium", "center", "project"]):
                        question = f"In which city was the {entity} project or event held?"
                        correct_answer = entity
                        incorrect_answers = [e[0] for e in entities if e[1] == "GPE" and e[0] != entity]
                        incorrect_answers.extend(["Delhi", "Kolkata", "Chennai"][:3-len(incorrect_answers)])
                        logger.debug(f"Generated location-based question: {question}")
                        break
                    elif label == "ORG" and any(k in sentence_lower for k in ["collaborat", "partner", "program"]):
                        question = f"Which organization collaborated on the program mentioned with {entity}?"
                        correct_answer = entity
                        incorrect_answers = [e[0] for e in entities if e[1] == "ORG" and e[0] != entity]
                        incorrect_answers.extend(["TCS", "Infosys", "Wipro"][:3-len(incorrect_answers)])
                        logger.debug(f"Generated organization-based question: {question}")
                        break

            if not question:
                numbers = re.findall(r'\d+\.?\d*', sentence)
                sentence_lower = sentence.lower()
                if numbers and any(keyword in sentence_lower for keyword in ["crore", "percent", "km", "%"]):
                    number = numbers[0]
                    if "crore" in sentence_lower:
                        question = f"What is the approximate budget mentioned in the news?"
                        correct_answer = f"{number} crore"
                        incorrect_answers = [f"{float(number)*2} crore", f"{float(number)/2} crore", f"{float(number)+100} crore"]
                        logger.debug(f"Generated crore-based question: {question}")
                    elif any(k in sentence_lower for k in ["percent", "%"]):
                        question = f"What is the projected percentage value mentioned in the news?"
                        correct_answer = f"{number}%"
                        incorrect_answers = [f"{float(number)+1}%", f"{float(number)-1}%", f"{float(number)+2}%"]
                        logger.debug(f"Generated percent-based question: {question}")
                    elif "km" in sentence_lower:
                        question = f"What is the length of the project mentioned in the news?"
                        correct_answer = f"{number} km"
                        incorrect_answers = [f"{float(number)*2} km", f"{float(number)/2} km", f"{float(number)+10} km"]
                        logger.debug(f"Generated km-based question: {question}")

            if question and correct_answer and len(incorrect_answers) >= 3:
                answers = incorrect_answers[:3] + [correct_answer]
                random.shuffle(answers)
                correct_idx = answers.index(correct_answer)
                quizzes.append({
                    'question': question,
                    'answers': answers,
                    'correct': correct_idx
                })
                logger.debug(f"Added quiz: {question} | Correct: {correct_answer}")

        return quizzes[:10]

    def fallback_quiz_extraction(self, text):
        """Fallback method for Hindi and English text without spaCy."""
        logger.debug("Using fallback quiz extraction")
        quizzes = []
        sentences = re.split(r'\n|\।\s+|\.\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        logger.debug(f"Fallback: Extracted {len(sentences)} sentences")

        hindi_keywords = {
            "उद्घाटन": "inaugurated",
            "लॉन्च": "launched",
            "शुरू": "started",
            "सहयोग": "collaborated",
            "प्रतिशत": "percent",
            "करोड़": "crore",
            "किलोमीटर": "km"
        }

        for i, sentence in enumerate(sentences[:10]):
            question = None
            correct_answer = None
            incorrect_answers = []
            sentence_lower = sentence.lower()

            for hindi, english in hindi_keywords.items():
                sentence_lower = sentence_lower.replace(hindi, english)

            numbers = re.findall(r'\d+\.?\d*', sentence_lower)
            logger.debug(f"Sentence {i+1}: {sentence} | Numbers: {numbers}")

            if numbers:
                number = numbers[0]
                if "crore" in sentence_lower:
                    question = f"What is the approximate budget mentioned in the news?"
                    correct_answer = f"{number} crore"
                    incorrect_answers = [f"{float(number)*2} crore", f"{float(number)/2} crore", f"{float(number)+100} crore"]
                    logger.debug(f"Fallback: Generated crore-based question: {question}")
                elif any(k in sentence_lower for k in ["percent", "%"]):
                    question = f"What is the projected percentage value mentioned in the news?"
                    correct_answer = f"{number}%"
                    incorrect_answers = [f"{float(number)+1}%", f"{float(number)-1}%", f"{float(number)+2}%"]
                    logger.debug(f"Fallback: Generated percent-based question: {question}")
                elif "km" in sentence_lower:
                    question = f"What is the length of the project mentioned in the news?"
                    correct_answer = f"{number} km"
                    incorrect_answers = [f"{float(number)*2} km", f"{float(number)/2} km", f"{float(number)+10} km"]
                    logger.debug(f"Fallback: Generated km-based question: {question}")

            if not question:
                names = re.findall(r'[A-Z][a-z]+ [A-Z][a-z]+|[\u0900-\u097F]+ [\u0900-\u097F]+', sentence)
                if names and any(k in sentence_lower for k in ["inaugurated", "launched", "started"]):
                    correct_answer = names[0]
                    question = f"Who was involved in the event mentioned in the news?"
                    incorrect_answers = names[1:3] if len(names) > 1 else []
                    incorrect_answers.extend(["Rahul Gandhi", "Amit Shah", "Sonia Gandhi"][:3-len(incorrect_answers)])
                    logger.debug(f"Fallback: Generated person-based question: {question}")

            if question and correct_answer and len(incorrect_answers) >= 3:
                answers = incorrect_answers[:3] + [correct_answer]
                random.shuffle(answers)
                correct_idx = answers.index(correct_answer)
                quizzes.append({
                    'question': question,
                    'answers': answers,
                    'correct': correct_idx
                })
                logger.debug(f"Fallback: Added quiz: {question} | Correct: {correct_answer}")

        logger.debug(f"Fallback: Generated {len(quizzes)} quizzes")
        return quizzes[:10]

    def start(self, update, context):
        update.message.reply_text("Send current affairs text (Hindi or English), and I'll generate quizzes automatically. Use /generate to start quizzes.")
        logger.info("Received /start command")

    def receive_data(self, update, context):
        text = update.message.text
        logger.info(f"Received current affairs text: {text[:500]}...")
        self.quizzes = self.extract_quiz_data(text)
        if self.quizzes:
            update.message.reply_text(f"Generated {len(self.quizzes)} quizzes. Use /generate to start.")
            with open('quizzes.json', 'w') as f:
                json.dump(self.quizzes, f)
            logger.info(f"Saved {len(self.quizzes)} quizzes to quizzes.json")
        else:
            update.message.reply_text("Could not generate quizzes. Please provide detailed current affairs text with numbers or names.")
            logger.warning("No quizzes generated from input text")

    def generate_quiz(self, update, context):
        if not self.quizzes:
            update.message.reply_text("No quizzes available. Send current affairs text first.")
            logger.warning("Attempted /generate with no quizzes")
            return
        
        chat_id = update.message.chat_id
        self.current_quiz = 0
        self.user_data[chat_id] = {'score': 0, 'total': len(self.quizzes)}
        logger.info(f"Starting quiz in chat {chat_id} with {len(self.quizzes)} questions")
        
        context.job_queue.run_repeating(
            self.send_quiz,
            interval=15,
            first=0,
            context={'chat_id': chat_id, 'update': update},
            name=f"quiz_{chat_id}"
        )

    def send_quiz(self, context):
        job = context.job
        chat_id = job.context['chat_id']
        update = job.context['update']

        if self.current_quiz >= len(self.quizzes):
            score = self.user_data[chat_id]['score']
            total = self.user_data[chat_id]['total']
            context.bot.send_message(chat_id=chat_id, text=f"Quiz finished! Your score: {score}/{total}")
            logger.info(f"Quiz finished in chat {chat_id}. Score: {score}/{total}")
            self.current_quiz = None
            job.schedule_removal()
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
            logger.info(f"Sent quiz {self.current_quiz+1}/{len(self.quizzes)} to chat {chat_id}: {quiz['question']}")
            self.current_quiz += 1
        except telegram.error.NetworkError as e:
            logger.error(f"Network error sending poll to chat {chat_id}: {e}")
            context.bot.send_message(chat_id=chat_id, text="Network issue. Retrying in 10 seconds...")
            context.job_queue.run_once(
                lambda c: self.send_quiz(c),
                10,
                context=job.context
            )

    def handle_poll_answer(self, update, context):
        poll = update.poll
        chat_id = context.bot_data.get(poll.id)
        if not chat_id:
            logger.warning(f"No chat_id found for poll {poll.id}")
            return
        
        if poll.correct_option_id in [opt.id for opt in poll.options if opt.voter_count > 0]:
            self.user_data[chat_id]['score'] += 1
            logger.debug(f"Correct answer for poll in chat {chat_id}. Score: {self.user_data[chat_id]['score']}")

    def main(self):
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("start", self.start))
        dp.add_handler(CommandHandler("generate", self.generate_quiz))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.receive_data))
        dp.add_handler(PollHandler(self.handle_poll_answer, pass_chat_data=True, pass_user_data=True))

        try:
            updater.start_polling(timeout=30)
            logger.info("Bot started polling")
            updater.idle()
        except telegram.error.NetworkError as e:
            logger.error(f"Failed to start polling: {e}")
            raise

if __name__ == "__main__":
    bot = QuizBot()
    bot.main()
