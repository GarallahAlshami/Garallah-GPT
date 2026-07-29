import os
import logging
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    logger.error("TELEGRAM_BOT_TOKEN or GEMINI_API_KEY is not set.")
    exit(1)

# Initialize Gemini Client
# The genai.Client() automatically picks up GEMINI_API_KEY from the environment
try:
    gemini_client = genai.Client()
except Exception as e:
    logger.error(f"Failed to initialize Gemini client: {e}")
    exit(1)

# Dictionary to store conversation history per user
# Format: {user_id: interaction_id}
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = (
        f"مرحباً {user.first_name}! 👋\n\n"
        "أنا مساعدك الذكي المدعوم بـ Google Gemini. 🤖\n"
        "يمكنك التحدث معي بحرية، أو استخدام الأوامر التالية:\n"
        "/image <وصف> - لتوليد صورة بناءً على وصفك.\n"
        "/clear - لمسح سجل المحادثة والبدء من جديد.\n"
        "/help - لعرض هذه القائمة."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "الأوامر المتاحة:\n"
        "/start - بدء المحادثة\n"
        "/image <وصف> - توليد صورة (مثال: /image قطة تلعب بالكرة)\n"
        "/clear - مسح سجل المحادثة\n"
        "/help - عرض هذه القائمة"
    )
    await update.message.reply_text(help_text)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the conversation history for the user."""
    user_id = update.effective_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await update.message.reply_text("تم مسح سجل المحادثة بنجاح! يمكنك البدء من جديد. 🧹")

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate an image using Gemini Nano Banana (gemini-2.5-flash-image)."""
    if not context.args:
        await update.message.reply_text("الرجاء كتابة وصف للصورة بعد الأمر. مثال:\n/image قطة في الفضاء")
        return

    prompt = " ".join(context.args)
    message = await update.message.reply_text("جاري توليد الصورة... 🎨 يرجى الانتظار.")

    try:
        # Use Nano Banana (gemini-2.5-flash-image) as recommended by Google for image generation
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash-image',
            contents=prompt,
        )
        
        # Extract image bytes from the response
        # The response contains content parts which may include image data
        image_bytes = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    break
        
        if image_bytes:
            # Send the image back to the user
            await update.message.reply_photo(
                photo=image_bytes,
                caption=f"الصورة المطلوبة: {prompt}"
            )
            await message.delete()
        else:
            await message.edit_text("عذراً، لم أتمكن من توليد الصورة. يرجى المحاولة بوصف مختلف.")
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await message.edit_text("حدث خطأ أثناء توليد الصورة. قد يكون الوصف مخالفاً للسياسات أو هناك مشكلة في الخادم.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages and respond using Gemini."""
    user_id = update.effective_user.id
    user_text = update.message.text

    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        # Check if user has an active session
        previous_interaction_id = user_sessions.get(user_id)
        
        # Call Gemini API using Interactions API for stateful conversation
        kwargs = {
            "model": "gemini-3.5-flash",
            "input": user_text
        }
        
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id
            
        interaction = gemini_client.interactions.create(**kwargs)
        
        # Save the new interaction ID for the next turn
        user_sessions[user_id] = interaction.id
        
        # Send the response back to the user
        response_text = interaction.output_text
        if response_text:
            await update.message.reply_text(response_text)
        else:
            await update.message.reply_text("عذراً، لم أتمكن من صياغة رد مناسب.")
            
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("عذراً، حدث خطأ أثناء معالجة رسالتك. يرجى المحاولة مرة أخرى لاحقاً.")

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("image", generate_image))

    # Message handler for regular text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
