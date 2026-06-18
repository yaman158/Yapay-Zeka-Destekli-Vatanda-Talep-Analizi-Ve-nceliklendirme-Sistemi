import imaplib
import email
from email.header import decode_header
import sqlite3

# --- AYARLAR ---
EMAIL_ADRESI = "kamalfamily1999@gmail.com"
UYGULAMA_SIFRESI = "mbpg eeub qimc cypi"
IMAP_SUNUCUSU = "imap.gmail.com"
DB_YOLU = r"D:\Yaman\Python\pythonProject12\telekom.db"

# SADECE BU ADRESTEN GELEN MAİLLERİ ÇEKECEĞİZ:
HEDEF_GONDEREN = "ykf20002@gmail.com"


def mailleri_cek_ve_kaydet():
    print(f"Sunucuya bağlanılıyor... Sadece {HEDEF_GONDEREN} adresinden gelen mailler aranacak.")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SUNUCUSU)
        mail.login(EMAIL_ADRESI, UYGULAMA_SIFRESI)
        mail.select("inbox")

        # 1. YENİ KURAL: Hem okunmamış olsun, hem de belirlediğimiz kişiden gelsin
        status, messages = mail.search(None, 'UNSEEN', 'FROM', f'"{HEDEF_GONDEREN}"')

        # messages[0] byte formatında boşlukla ayrılmış id'ler döndürür ("1 2 3" gibi)
        mail_id_list = messages[0].split()

        if not mail_id_list:
            print("Belirtilen kriterlere uygun yeni mail yok.")
            return

        conn = sqlite3.connect(DB_YOLU)
        cursor = conn.cursor()

        for mail_id in mail_id_list:
            res, msg_data = mail.fetch(mail_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Konuyu ayıkla
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")

                    # Göndereni ayıkla
                    sender = msg.get("From")

                    # --- 2. YENİ KURAL: REPLY BİLGİLERİNİ ÇEKME ---
                    reply_to = msg.get("Reply-To", "Belirtilmemiş")
                    in_reply_to = msg.get("In-Reply-To")

                    is_reply = "EVET" if in_reply_to else "HAYIR (Yeni Mail)"

                    # İçeriği ayıkla
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # Veritabanına kaydet
                    cursor.execute("""
                        INSERT INTO GelenMailler (Gonderen, Konu, Icerik, Durum)
                        VALUES (?, ?, ?, 'Bekliyor')
                    """, (sender, subject, body))

                    print("-" * 40)
                    print(f"YENİ MAİL YAKALANDI!")
                    print(f"Gönderen: {sender}")
                    print(f"Konu: {subject}")
                    print(f"Bu Bir Cevap mı? (Reply): {is_reply}")
                    print(f"Yanıtlanacak Adres (Reply-To): {reply_to}")
                    print("-" * 40)

        conn.commit()
        conn.close()
        mail.logout()
        print("İşlem başarıyla tamamlandı.")

    except Exception as e:
        print(f"Hata oluştu: {e}")


if __name__ == "__main__":
    mailleri_cek_ve_kaydet()