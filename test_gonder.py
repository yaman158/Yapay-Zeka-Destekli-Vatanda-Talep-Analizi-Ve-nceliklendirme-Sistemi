import sqlite3

# Veritabanına bağlan
conn = sqlite3.connect("telekom.db")
cursor = conn.cursor()

# C# uygulamasının yapacağı işi taklit edip veritabanına sahte bir mail yazıyoruz
cursor.execute("""
    INSERT INTO GelenMailler (Gonderen, Konu, Icerik, Durum)
    VALUES (?, ?, ?, 'Bekliyor')
""", (
    "ahmet.muster2i@gmail.com",
    "İnternetim Koptu2 Acil!",
    "Merhaba, dünden beri internetim yok. Evden çalışıyorum ve çok mağdurum. Lütfen acil destek olun."
))

conn.commit()
conn.close()

print("Test maili veritabanına başarıyla eklendi! Şimdi diğer terminaldeki ajan ekranına bak :)")