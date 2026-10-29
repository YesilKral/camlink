# CamLink – Aşama 1

iPhone'u fiziksel olarak hareket ettir, PC'deki sanal kamera aynı şekilde hareket etsin.
Bu aşamada **oyun kamerası henüz bağlı değil**: telefon → PC hattı kurulur ve PC penceresinde
test edilir. Poz, `127.0.0.1:9051` adresine UDP/JSON olarak yayınlanır (Aşama 3'te oyuna bağlanacak).

```
iPhone (ARKit) --Wi-Fi/UDP:9050--> PC programı --UDP 127.0.0.1:9051--> (Aşama 3: oyun kamerası)
```

## 1) PC'ye Python kur
1. https://www.python.org/downloads/ adresinden Python 3.11 veya yenisini indir.
2. Kurulumda en altta **"Add python.exe to PATH"** kutusunu işaretle, sonra Install.
3. `pc` klasöründe komut satırı aç ve `python selftest.py` yaz. "Tüm testler geçti." görmelisin.

## 2) iPhone uygulamasını derle (Mac gerekmez)
1. github.com'da yeni bir **private** repo aç.
2. Bu klasördeki her şeyi (`.github`, `ios`, `pc` klasörleri dahil) repoya yükle (Add file → Upload files).
   `.github` klasörü yüklenmezse: Add file → Create new file → adı `.github/workflows/build.yml`
   yaz ve bu projedeki dosyanın içeriğini yapıştır.
3. Repoda **Actions** sekmesi → "iPhone uygulamasini derle" → **Run workflow**.
4. Yaklaşık 5 dakika sonra bitince çalıştırmanın sayfasının altındaki **CamLink-ipa** dosyasını indir,
   zip'ten `CamLink.ipa` çıkar.
5. Derleme kırmızı biterse hata kaydını (log) kopyalayıp bana gönder.

## 3) Telefona yükle (Sideloadly, ücretsiz Apple ID ile)
1. https://sideloadly.io adresinden Sideloadly'yi kur. iTunes ve iCloud'un **apple.com sürümleri** gerekir
   (Microsoft Store sürümleri olmaz).
2. iPhone'u kabloyla bağla, `CamLink.ipa` dosyasını Sideloadly'ye sürükle, Apple ID'ni yaz, Start.
3. iPhone'da: Ayarlar → Genel → VPN ve Aygıt Yönetimi → geliştirici profiline **Güven**.
4. Ayarlar → Gizlilik ve Güvenlik → **Geliştirici Modu** aç (telefon yeniden başlar).
5. Ücretsiz Apple ID ile yüklenen uygulama **7 gün** sonra açılmaz olur; Sideloadly ile yeniden yükle.

## 4) Çalıştır
1. PC'de `pc\baslat.bat` dosyasına çift tıkla. Windows Güvenlik Duvarı sorarsa **Özel ağlara izin ver**.
2. Pencerede **IP** ve **KOD** görünür.
3. Telefon ve PC **aynı Wi-Fi**'de olsun. Telefonda CamLink'i aç, kamera ve yerel ağ iznini ver,
   IP ile kodu yaz, **Bağlan**.
4. Telefonu arka kamerası kapanmadan dik tut, "Merkezle"ye bas ve hareket ettir. PC penceresinde
   üstten görünümde üçgen (kamera) hareket eder.

## Kontroller
| Telefonda | Ne yapar |
|---|---|
| Telefonu taşı / çevir | Kamera konumu ve bakışı |
| Joystick | Kameranın baktığı yöne ilerle/geri/sağa/sola |
| Yükseklik kaydırıcı | Yukarı/aşağı (bırakınca durur) |
| Merkezle | Sıfır noktası = şu anki konum ve yön |
| CAR VIEW / FREECAM | Modu PC'ye bildirir (Aşama 3'te kullanılacak) |

PC penceresinde: konum çarpanı (telefonda 1 m = oyunda kaç m), yumuşatma, hızlar.

## Sorun giderme
- **"PC'den yanıt yok"**: IP/kod doğru mu? Aynı Wi-Fi mı? Güvenlik duvarında Python'a izin verdin mi?
  Misafir ağı ve bazı modemlerde "istemci izolasyonu" cihazların birbirini görmesini engeller.
- **Takip "limited"**: ortam çok karanlık/düz olabilir, kamerayı kapatma, daha yavaş hareket et.
- **Roll (yan yatış) ters**: PC penceresinde "Roll yönü normal" kutusunu çevir.
- **Telefon bağlanıyor ama kamera ters yöne gidiyor**: bana hangi eksenin ters olduğunu söyle.

## Çıkış formatı (Aşama 3 için)
```json
{"t":1730000000.1,"seq":42,"pos":[x,y,z],"yaw":0.0,"pitch":0.0,"roll":0.0,"mode":"free","tracking":"normal"}
```
Metre ve derece; x sağ, y yukarı, z ileri; merkezle anına göre.
