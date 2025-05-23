import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PollHandler
import re
import random
from config import TOKEN, PROXY_URL
import json
import logging
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests import Session

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class QuizBot:
    def __init__(self):
        self.quizzes = []
        self.current_quiz = None
        self.user_data = {}

    def extract_quiz_data(self, text):
        # Simple regex to extract questions and answers from structured text
        # Expected format: "Q: Question? A1: Answer1 A2: Answer2 A3: Answer3 A4: Answer4 Correct: A1"
        quizzes = []
        pattern = r'Q:\s*(.*?)\?\s*A1:\s*(.*?)\s*A2:\s*(.*?)\s*A3:\s*(.*?)\s*A4:\s*(.*?)\s*Correct:\s*(A\d)'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            question, a1, a2, a3, a4, correct = match
            answers = [a1.strip(), a2.strip(), a3.strip(), a4.strip()]
            correct_idx = int(correct[1]) - 1
            quizzes.append({
                'question': question.strip(),
                'answers': answers,
                'correct': correct_idx
            })
        return quizzes[:10]  # Limit to 10 quizzes

    def start(self, update, context):
        update.message.reply_text("Send current affairs data to generate quizzes, or use /generate to start quizzes in this chat.")

    def receive_data(self, update, context):
        text = update.message.text
        self.quizzes = self.extract_quiz_data(text)
        if self.quizzes:
            update.message.reply_text(f"Received data. {len(self.quizzes)} quizzes generated. Use /generate to start.")
            # Save quizzes to a file
            with open('quizzes.json', 'w') as f:
                json.dump(self.quizzes, f)
        else:
            update.message.reply_text("No valid quiz data found. Please use format: Q: Question? A1: Ans1 A2: Ans2 A3: Ans3 A4: Ans4 Correct: A1")

    def generate_quiz(self, update, context):
        if not self.quizzes:
            update.message.reply_text("No quizzes available. Send current affairs data first.")
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
                explanation="Check the current affairs data for details.",
                timeout=30  # Increased timeout
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
    # Configure retries for network requests
    retries = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session = Session()
    session.mount('https://', HTTPAdapter(max_retries=retries))
    
    # Apply proxy if provided
    request_kwargs = {'session': session}
    if PROXY_URL:
        request_kwargs['proxy_url'] = PROXY_URL
        logger.info(f"Using proxy: {PROXY_URL}")
    
    updater = Updater(TOKEN, use_context=True, request_kwargs=request_kwargs)
    dp = updater.dispatcher
    bot = QuizBot()

    dp.add_handler(CommandHandler("start", bot.start))
    dp.add_handler(CommandHandler("generate", bot.generate_quiz))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, bot.receive_data))
    dp.add_handler(PollHandler(bot.handle_poll_answer, pass_chat_data=True, pass_user_data=True))

    try:
        updater.start_polling(timeout=30)  # Increased polling timeout
        logger.info("Bot started polling")
        updater.idle()
    except telegram.error.NetworkError as e:
        logger.error(f"Failed to start polling: {e}")
        raise

if __name__ == "__main__":
    main()
