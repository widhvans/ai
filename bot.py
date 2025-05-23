import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PollHandler, JobQueue
import random
from config import TOKEN
import json
import logging
import re
from datetime import datetime

# Configure detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler('bot.log'),  # Save logs to bot.log
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

class QuizBot:
    def __init__(self):
        self.quizzes = []
        self.current_quiz = None
        self.user_data = {}
        self.job_queue = None

    def extract_quiz_data(self, text):
        """Generate quizzes from unstructured current affairs text (English or Hindi)."""
        logger.debug("Starting quiz extraction from text: %s", text[:200] + "..." if len(text) > 200 else text)
        quizzes = []
        
        # Split text into sentences (works for both English and Hindi)
        sentences = re.split(r'\n|\.\s+|।\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        logger.debug("Extracted %d sentences", len(sentences))

        # Entity extraction rules
        person_pattern = r'([A-Za-z\s]+|[\u0900-\u097F\s]+)\s*(?:ने|inaugurated|launched)'
        place_pattern = r'(?:in|at|में)\s*([A-Za-z]+|[\u0900-\u097F\s]+)'
        org_pattern = r'(?:DRDO|WHO|IIT|UN|[\u0900-\u097F\s]+)\s*(?:collaborated|सहयोग)'
        number_pattern = r'(\d+\.?\d*)\s*(crore|percent|%|किलोमीटर|किमी|crores|करोड़)'

        # Store entities for incorrect options
        persons = []
        places = []
        orgs = []

        for sentence in sentences[:10]:  # Limit to 10 quizzes
            question = None
            correct_answer = None
            incorrect_answers = []
            
            # Extract entities
            person_matches = re.findall(person_pattern, sentence, re.IGNORECASE)
            place_matches = re.findall(place_pattern, sentence, re.IGNORECASE)
            org_matches = re.findall(org_pattern, sentence, re.IGNORECASE)
            number_matches = re.findall(number_pattern, sentence, re.IGNORECASE)

            persons.extend([m.strip() for m in person_matches])
            places.extend([m.strip() for m in place_matches])
            orgs.extend([m.strip() for m in org_matches])

            logger.debug("Sentence: %s", sentence)
            logger.debug("Persons: %s, Places: %s, Orgs: %s, Numbers: %s", person_matches, place_matches, org_matches, number_matches)

            # Strategy 1: Person-based question
            if person_matches and any(keyword in sentence.lower() for keyword in ["inaugurated", "launched", "उद्घाटन", "शुरू"]):
                person = person_matches[0].strip()
                question = f"Who inaugurated or launched the event/project mentioned in the news? / किसने समाचार में उल्लिखित घटना/परियोजना का उद्घाटन या शुरूआत की?"
                correct_answer = person
                incorrect_answers = [p for p in persons if p != person][:2]
                incorrect_answers.extend(["Rahul Gandhi", "Amit Shah", "Sonia Gandhi"][:3-len(incorrect_answers)])
                logger.debug("Person-based quiz generated: Q: %s, A: %s", question, correct_answer)

            # Strategy 2: Place-based question
            elif place_matches and any(keyword in sentence.lower() for keyword in ["stadium", "center", "centre", "स्टेडियम", "केंद्र"]):
                place = place_matches[0].strip()
                question = f"In which place is the mentioned stadium or center located? / उल्लिखित स्टेडियम या केंद्र किस स्थान पर स्थित है?"
                correct_answer = place
                incorrect_answers = [p for p in places if p != place][:2]
                incorrect_answers.extend(["Delhi", "Kolkata", "Chennai"][:3-len(incorrect_answers)])
                logger.debug("Place-based quiz generated: Q: %s, A: %s", question, correct_answer)

            # Strategy 3: Organization-based question
            elif org_matches and any(keyword in sentence.lower() for keyword in ["collaborated", "सहयोग", "partnership"]):
                org = org_matches[0].strip()
                question = f"Which organization collaborated on the mentioned project? / किस संगठन ने उल्लिखित परियोजना पर सहयोग किया?"
                correct_answer = org
                incorrect_answers = [o for o in orgs if o != org][:2]
                incorrect_answers.extend(["TCS", "Infosys", "Wipro"][:3-len(incorrect_answers)])
                logger.debug("Org-based quiz generated: Q: %s, A: %s", question, correct_answer)

            # Strategy 4: Numeric question
            elif number_matches:
                number, unit = number_matches[0]
                if unit.lower() in ["crore", "crores", "करोड़"]:
                    question = f"What is the approximate budget mentioned in the news? / समाचार में उल्लिखित अनुमानित बजट क्या है?"
                    correct_answer = f"{number} crore"
                    incorrect_answers = [f"{float(number)*2} crore", f"{float(number)/2} crore", f"{float(number)+100} crore"]
                elif unit.lower() in ["percent", "%"]:
                    question = f"What is the projected percentage value mentioned? / उल्लिखित अनुमानित प्रतिशत मूल्य क्या है?"
                    correct_answer = f"{number}%"
                    incorrect_answers = [f"{float(number)+1}%", f"{float(number)-1}%", f"{float(number)+2}%"]
                elif unit.lower() in ["kilometer", "किलोमीटर", "किमी"]:
                    question = f"What is the length of the mentioned project? / उल्लिखित परियोजना की लंबाई क्या है?"
                    correct_answer = f"{number} km"
                    incorrect_answers = [f"{float(number)*2} km", f"{float(number)/2} km", f"{float(number)+10} km"]
                logger.debug("Number-based quiz generated: Q: %s, A: %s", question, correct_answer)

            # Ensure valid quiz
            if question and correct_answer and len(set(incorrect_answers)) >= 3:
                answers = list(set(incorrect_answers[:3])) + [correct_answer]
                random.shuffle(answers)
                correct_idx = answers.index(correct_answer)
                quizzes.append({
                    'question': question,
                    'answers': answers,
                    'correct': correct_idx
                })
                logger.debug("Quiz added: %s", quizzes[-1])

        logger.info("Generated %d quizzes", len(quizzes))
        return quizzes[:10]

    def start(self, update, context):
        self.job_queue = context.job_queue
        update.message.reply_text("Send current affairs text (English or Hindi), and I'll generate quizzes. Use /generate to start quizzes (one every 15 seconds).")
        logger.info("Bot started by user: %s", update.message.from_user.id)

    def receive_data(self, update, context):
        text = update.message.text
        logger.debug("Received text from user %s: %s", update.message.from_user.id, text[:200])
        self.quizzes = self.extract_quiz_data(text)
        if self.quizzes:
            update.message.reply_text(f"Generated {len(self.quizzes)} quizzes. Use /generate to start.")
            # Save quizzes with timestamp
            with open('quizzes.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'quizzes': self.quizzes
                }, f, ensure_ascii=False)
            logger.info("Saved %d quizzes to quizzes.json", len(self.quizzes))
        else:
            update.message.reply_text("Could not generate quizzes. Ensure the text includes names, places, organizations, or numbers (e.g., crore, percent).")
            logger.warning("No quizzes generated from text")

    def generate_quiz(self, update, context):
        if not self.quizzes:
            update.message.reply_text("No quizzes available. Send current affairs text first.")
            logger.warning("Generate command called with no quizzes")
            return
        
        chat_id = update.message.chat_id
        self.current_quiz = 0
        self.user_data[chat_id] = {'score': 0, 'total': len(self.quizzes)}
        logger.info("Starting quiz for chat %s with %d quizzes", chat_id, len(self.quizzes))
        
        # Schedule first quiz
        context.job_queue.run_once(self.send_quiz_job, 0, context={'chat_id': chat_id})

    def send_quiz_job(self, context):
        """Job to send quizzes one by one with 15-second delay."""
        job_context = context.job.context
        chat_id = job_context['chat_id']
        
        if self.current_quiz >= len(self.quizzes):
            score = self.user_data[chat_id]['score']
            total = self.user_data[chat_id]['total']
            context.bot.send_message(chat_id=chat_id, text=f"Quiz finished! Your score: {score}/{total}")
            logger.info("Quiz finished for chat %s: Score %d/%d", chat_id, score, total)
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
            logger.debug("Sent quiz %d to chat %s: %s", self.current_quiz + 1, chat_id, quiz['question'])
            self.current_quiz += 1
            
            # Schedule next quiz after 15 seconds
            if self.current_quiz <> self.quizzes:
                context.job_queue.run_once(self.send_quiz_job, 15, context={'chat_id': chat_id})
        except telegram.error.NetworkError as e:
            logger.error("Network error sending poll to chat %s: %s", chat_id, e)
            context.bot.send_message(chat_id=chat_id, text="Network issue. Retrying in 10 seconds...")
            context.job_queue.run_once(self.send_quiz_job, 10, context={'chat_id': chat_id})

    def handle_poll_answer(self, update, context):
        poll = update.poll
        chat_id = context.bot_data.get(poll.id)
        if not chat_id:
            logger.warning("No chat_id found for poll %s", poll.id)
            return
        
        if poll.correct_option_id in [opt.id for opt in poll.options if opt.voter_count > 0]:
            self.user_data[chat_id]['score'] += 1
            logger.debug("Correct answer for poll %s in chat %s", poll.id, chat_id)

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
        logger.error("Failed to start polling: %s", e)
        raise

if __name__ == "__main__":
    main()
