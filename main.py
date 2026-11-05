
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime
from datetime import datetime

class Settings(BaseSettings):
    BOT_TOKEN: str = "8854420928:AAE_1MIjK7i45yeUwt7mPbjWBAzTH494d7M"

config = Settings()

DATABASE_URL = "sqlite+aiosqlite:///job_bot.db"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class Applicant(Base):
    __tablename__ = "applicants"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    cv_file_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_applicant(telegram_id: int, full_name: str, phone: str, cv_file_id: str):
    async with async_session() as session:
        async with session.begin():
            new_applicant = Applicant(telegram_id=telegram_id, full_name=full_name, phone=phone, cv_file_id=cv_file_id)
            session.add(new_applicant)
            await session.commit()

class ApplyForm(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_cv = State()

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 التقديم على وظيفة", callback_data="start_apply")],
        [InlineKeyboardButton(text="📄 الوظائف المتاحة", callback_data="list_jobs")]
    ])
    await message.answer(
        f"أهلاً بك يا **{message.from_user.first_name}** في منصة **أبشر وتم** للتوظيف 🚀\n"
        "يمكنك استعراض الوظائف أو بدء التقديم مباشرة عبر الأزرار أدناه:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "start_apply")
async def start_apply_process(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("أهلاً بك. لنبدأ عملية التقديم.\n\nالرجاء إرسال **اسمك الثلاثي**:")
    await state.set_state(ApplyForm.waiting_for_full_name)
    await callback.answer()

@router.callback_query(F.data == "list_jobs")
async def list_jobs_process(callback: CallbackQuery):
    await callback.message.answer("💼 الوظائف المتاحة حالياً:\n\nلا توجد وظائف مفتوحة حالياً، تابعنا لتجديد القائمة قريباً!")
    await callback.answer()

@router.message(ApplyForm.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("ممتاز. الآن، الرجاء إرسال **رقم الجوال الخاص بك** (مثال: 0500000000):")
    await state.set_state(ApplyForm.waiting_for_phone)

@router.message(ApplyForm.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("رائع جداً. الخطوة الأخيرة: الرجاء إرسال سيرتك الذاتية بصيغة **PDF** فقط (كمستند):")
    await state.set_state(ApplyForm.waiting_for_cv)

@router.message(ApplyForm.waiting_for_cv, F.document)
async def process_cv(message: Message, state: FSMContext):
    document = message.document
    if not document.file_name.endswith('.pdf'):
        await message.answer("⚠️ عذراً، يجب أن يكون الملف بصيغة **PDF** فقط. أعد المحاولة:")
        return

    user_data = await state.get_data()
    try:
        await save_applicant(
            telegram_id=message.from_user.id,
            full_name=user_data.get("full_name"),
            phone=user_data.get("phone"),
            cv_file_id=document.file_id
        )
    except Exception:
        await message.answer("⚠️ حدث خطأ أثناء حفظ بياناتك. يرجى المحاولة لاحقاً.")
        await state.clear()
        return

    await message.answer(
        "✅ **تم حفظ طلبك في قاعدة البيانات بنجاح!**\n\n"
        f"👤 الاسم: {user_data.get('full_name')}\n"
        f"📱 الجوال: {user_data.get('phone')}\n"
        "📎 تم حفظ الـ CV بنجاح في النظام.\n\n"
        "سنقوم بمراجعة طلبك والتواصل معك قريباً.",
        parse_mode="Markdown"
    )
    await state.clear()

@router.message(ApplyForm.waiting_for_cv)
async def process_cv_invalid(message: Message):
    await message.answer("⚠️ يرجى إرسال ملف سيرتك الذاتية كـ **مستند (Document)** بصيغة PDF وليس كنص عادي.")

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
