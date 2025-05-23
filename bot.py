import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PollHandler, JobQueue
import requests
import random
from config import TOKEN, RAPIDAPI_KEY
import json
import logging
import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
import time
from datetime import datetime, timedelta

# Download NLTK resources
nltk.download('punkt')
nltk.download('stopwords')

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

class QuizBot:
    def __init__(self):
        self.quizzes = []
        self.current_quiz = None
        self.user_data = {}
        self.question_timeout = 30  # Seconds per question

    def call_prepai_api(self, text):
        """Use PrepAI API for question generation."""
        if not RAPIDAPI_KEY:
            logger.warning("RapidAPI key missing. Falling back to NLTK.")
            return None
        try:
            headers = {
                "x-rapidapi-key": RAPIDAPI_KEY,
                "x-rapidapi-host": "prepai-generate-questions.p.rapidapi.com",
                "Content-Type": "application/json"
            }
            payload = {
                "content": text,
                "question_type": ["multiple_choice", "true_false", "fill_in_the_blank"],
                "difficulty": "medium"
            }
            response = requests.post(
                "https://prepai-generate-questions.p.rapidapi.com/generate",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(f"PrepAI API response: {data}")
            return data.get('questions', [])
        except Exception as e:
            logger.error(f"PrepAI API error: {e}")
            return None

    def extract_quiz_data(self, text):
        """Generate quizzes from unstructured current affairs text."""
        logger.debug(f"Processing input text: {text[:1000]}...")
        quizzes = []

        # Try PrepAI API first
        prepai_questions = self.call_prepai_api(text)
        if prepai_questions:
            for q in prepai_questions[:10]:
                question = q.get('question')
                correct_answer = q.get('correct_answer')
                options = q.get('options', [])
                if question and correct_answer and len(options) >= 4:
                    answers = options[:3] + [correct_answer]
                    random.shuffle(answers)
                    correct_idx = answers.index(correct_answer)
                    quizzes.append({
                        'question': question,
                        'answers': answers,
                        'correct': correct_idx
                    })
                    logger.debug(f"PrepAI quiz: {question} | Correct: {correct_answer}")
        else:
            logger.info("Using NLTK fallback for quiz generation")
            quizzes.extend(self.fallback_quiz_extraction(text))

        logger.debug(f"Generated {len(quizzes)} quizzes")
        return quizzes[:10]

    def fallback_quiz_extraction(self, text):
        """Fallback method using NLTK for Hindi and English text."""
        logger.debug("Using NLTK fallback quiz extraction")
        quizzes = []
        sentences = sent_tokenize(text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        logger.debug(f"Fallback: Extracted {len(sentences)} sentences")

        hindi_keywords = {
            "उद्घाटन": "inaugurated",
            "लॉन्च": "launched",
            "शुरू": "started",
            "सहयोग": "collaborated",
            "प्रतिशत": "percent",
            "करोड़": "crore",
            "किलोमीटर": "km",
            "सम्मानित": "honored",
            "परियोजना": "project",
            "पुरस्कार": "awarded"
        }

        stop_words = set(stopwords.words('english')).union(['है', 'के', 'में', 'से', 'का', 'की', 'को'])

        for i, sentence in enumerate(sentences[:10]):
            question = None
            correct_answer = None
            incorrect_answers = []
            sentence_lower = sentence.lower()

            # Map Hindi keywords
            for hindi, english in hindi_keywords.items():
                sentence_lower = sentence_lower.replace(hindi, english)

            # Extract names and numbers
            tokens = word_tokenize(sentence)
            names = [t for t in tokens if (t[0].isupper() or t[0] in 'ऀ-ॿ') and t not in stop_words]
            numbers = re.findall(r'\d+\.?\d*', sentence_lower)
            logger.debug(f"Sentence {i+1}: {sentence} | Names: {names} | Numbers: {numbers}")

            # Person-based questions
            if names and any(k in sentence_lower for k in ["inaugurated", "launched", "started", "honored", "awarded"]):
                correct_answer = names[0]
                question = f"Who was involved in the event mentioned in the news?"
                incorrect_answers = names[1:3] if len(names) > 1 else []
                incorrect_answers.extend(["Rahul Gandhi", "Amit Shah", "Sonia Gandhi"][:3-len(incorrect_answers)])
                logger.debug(f"Fallback: Generated person-based question: {question}")

            # Numeric questions
            elif numbers:
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

            # Location-based questions
            elif names and any(k in sentence_lower for k in ["project", "stadium", "center"]):
                correct_answer = names[0]
                question = f"In which location was the project or event mentioned in the news held?"
                incorrect_answers = names[1:3] if len(names) > 1 else []
                incorrect_answers.extend(["Delhi", "Kolkata", "Chennai"][:3-len(incorrect_answers)])
                logger.debug(f"Fallback: Generated location-based question: {question}")

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
            update.message.reply_text("Could not generate quizzes. Please provide detailed current affairs text with numbers, names, or events.")
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
        
        # Start quiz immediately
        self.send_quiz(context, {'chat_id': chat_id, 'update': update})

    def send_quiz(self, context, job_context):
        chat_id = job_context['chat_id']
        update = job_context['update']

        if self.current_quiz >= len(self.quizzes):
            score = self.user_data[chat_id]['score']
            total = self.user_data[chat_id]['total']
            context.bot.send_message(chat_id=chat_id, text=f"Quiz finished! Your score: {score}/{total}")
            logger.info(f"Quiz finished in chat {chat_id}. Score: {score}/{total}")
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
                timeout=self.question_timeout
            )
            context.bot_data[message.poll.id] = chat_id
            logger.info(f"Sent quiz {self.current_quiz+1}/{len(self.quizzes)} to chat {chat_id}: {quiz['question']}")

            timer_message = context.bot.send_message(
                chat_id=chat_id,
                text=f"Time remaining: {self.question_timeout} seconds"
            )
            context.job_queue.run_once(
                self.update_timer,
                1,
                context={
                    'chat_id': chat_id,
                    'message_id': timer_message.message_id,
                    'end_time': datetime.now() + timedelta(seconds=self.question_timeout)
                },
                name=f"timer_{chat_id}_{self.current_quiz}"
            )

            self.current_quiz += 1
            if self.current_quiz < len(self.quizzes):
                context.job_queue.run_once(
                    self.send_quiz,
                    10,
                    context=job_context,
                    name=f"quiz_{chat_id}_{self.current_quiz}"
                )
        except telegram.error.NetworkError as e:
            logger.error(f"Network error sending poll to chat {chat_id}: {e}")
            context.bot.send_message(chat_id=chat_id, text="Network issue. Retrying in 10 seconds...")
            context.job_queue.run_once(
                self.send_quiz,
                10,
                context=job_context
            )

    def update_timer(self, context):
        job = context.job
        chat_id = job.context['chat_id']
        message_id = job.context['message_id']
        end_time = job.context['end_time']
        remaining = int((end_time - datetime.now()).total_seconds())

        if remaining <= 0:
            try:
                context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Time's up!"
                )
            except telegram.error.BadRequest:
                logger.debug(f"Timer message {message_id} already deleted or edited")
            return

        try:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"Time remaining: {remaining} seconds"
            )
            context.job_queue.run_once(
                self.update_timer,
                1,
                context=job.context,
                name=f"timer_{chat_id}_{self.current_quiz}"
            )
        except telegram.error.BadRequest:
            logger.debug(f"Timer message {message_id} already deleted or edited")

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
