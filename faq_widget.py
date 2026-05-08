from PySide6 import QtCore, QtWidgets, QtGui

class FAQWidget(QtWidgets.QWidget):
    """
    Yardım ve sıkça sorulan sorular (SSS).
    Arama özellikleri ve olası başlatma sorunları hakkında bilgiler içerir.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Başlık
        title_label = QtWidgets.QLabel("Yardım ve Sıkça Sorulan Sorular")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #8ecfff; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Alt Başlık
        subtitle_label = QtWidgets.QLabel("Uygulama kullanımı ve karşılaşılan sorunlar için hızlı rehber.")
        subtitle_label.setStyleSheet("font-size: 14px; color: #b0b0b0; margin-bottom: 20px;")
        layout.addWidget(subtitle_label)

        # FAQ Tab Widget
        self.faq_tabs = QtWidgets.QTabWidget()
        self.faq_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3f3f46; background: #1e1e1e; border-radius: 4px; }
            QTabBar::tab { background: #2d2d30; color: #d4d4d4; padding: 10px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #3f3f46; color: #8ecfff; font-weight: bold; }
            QTabBar::tab:hover { background: #333337; }
        """)

        # Tab 1: Arama Özellikleri
        self.faq_tabs.addTab(self._create_search_tab(), "🔍 Arama Özellikleri")
        
        # Tab 2: Başlatma ve Hatalar
        self.faq_tabs.addTab(self._create_troubleshooting_tab(), "🛠️ Sorun Giderme")
        
        # Tab 3: Genel Bilgiler
        self.faq_tabs.addTab(self._create_general_tab(), "ℹ️ Genel Bilgiler")

        layout.addWidget(self.faq_tabs, 1)

    def _create_search_tab(self):
        content = """
        <style>
            h3 { color: #8ecfff; margin-top: 20px; margin-bottom: 10px; }
            p { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            ul, ol { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            li { margin-bottom: 10px; }
            b { color: #ffffff; }
        </style>
        <h3>Nasıl Arama Yapabilirim?</h3>
        <p>Uygulamanın ana ekranında (Etkinlikler sekmesi) sol üst köşede bulunan arama kutusunu kullanabilirsiniz:</p>
        <ul>
            <li><b>Etkinlik İsmi:</b> Belirli bir etkinliği bulmak için adını yazmaya başlamanız yeterlidir.</li>
            <li><b>Hızlı Erişim:</b> Yazdığınız anda sonuçlar otomatik olarak filtrelenir.</li>
        </ul>

        <h3>Yüz Tanıma ile Arama</h3>
        <p>Belirli bir kişinin bulunduğu tüm fotoğrafları bulmak için:</p>
        <ol>
            <li><b>Kişiler</b> sekmesine gidin.</li>
            <li>Listeden aradığınız kişiyi seçin.</li>
            <li>Sağ panelde, o kişinin yer aldığı tüm etkinlikler ve fotoğraflar anında listelenecektir.</li>
        </ol>

        <h3>Yapay Zeka (AI) İçerik Araması</h3>
        <p>Fotoğrafların içeriğine göre arama yapmak için <b>Altyazı</b> sekmesini kullanabilirsiniz. Sistem fotoğrafları analiz ederek şu bilgileri çıkarır:</p>
        <ul>
            <li><b>Nesneler ve Sahneler:</b> "Mavi kravatlı adam", "el sıkışma", "meclis kürsüsü" gibi ifadelerle arama yapmanıza olanak tanır.</li>
            <li><b>Otomatik Etiketleme:</b> Fotoğraflar içeriğine göre otomatik olarak etiketlenir (örn: #toplantı, #resmi_tören).</li>
        </ul>

        <h3>Gelişmiş Arama İpuçları</h3>
        <ul>
            <li><b>VE (AND) Mantığı:</b> Birden fazla kelime yazdığınızda (örn: <code>mavi ceket</code>), sistem her iki kelimenin de geçtiği fotoğrafları bulur.</li>
            <li><b>Sıralama ve Tam Eşleşme:</b> Kelimelerin yan yana geçtiği sonuçlar otomatik olarak listenin en başında gösterilir.</li>
            <li><b>FTS Desteği:</b> Uygulama <i>Full-Text Search (Tam Metin Arama)</i> teknolojisini kullanır; böylece binlerce kayıt arasında çok hızlı arama yapabilirsiniz.</li>
            <li><b>Tırnak İşareti:</b> Tam ifade araması yapmak için kullanabilirsiniz (örn: <code>"mavi kravat"</code>). Bu şekilde arama yaptığınızda, kelimelerin tam olarak bu sırayla geçtiği sonuçlar en üstte gösterilir.</li>
        </ul>
        """
        return self._create_browser(content)

    def _create_troubleshooting_tab(self):
        content = """
        <style>
            h3 { color: #ff8e8e; margin-top: 20px; margin-bottom: 10px; }
            p { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            ul { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            li { margin-bottom: 10px; }
            code { background: #333; padding: 2px 4px; border-radius: 3px; color: #e2e2e2; }
            b { color: #ffffff; }
        </style>
        <h3>Uygulama Açılmıyor / Veritabanı Hatası</h3>
        <p>Uygulamanın çalışması için arka planda <b>Docker Desktop</b> uygulamasının açık olması gerekir.</p>
        <ul>
            <li>Lütfen Docker Desktop'ın çalıştığından emin olun.</li>
            <li>Eğer hata devam ediyorsa, terminalde <code>docker-compose up -d</code> komutunu çalıştırarak servisleri başlatmayı deneyin.</li>
        </ul>

        <h3>"Vector Extension" Hatası</h3>
        <p>Bu hata genellikle veritabanı ilk kurulurken bir eklentinin yüklenememesinden kaynaklanır. Lütfen sistemde PostgreSQL Vector eklentisinin aktif olduğundan emin olun.</p>

        <h3>Performans Sorunları</h3>
        <p>Yüz tanıma ve Yapay Zeka analizleri bilgisayarınızın işlemcisini ve belleğini yoğun kullanabilir:</p>
        <ul>
            <li>Büyük miktarda fotoğraf eklediğinizde işlemin tamamlanması zaman alabilir.</li>
            <li>İşlem devam ederken durum çubuğundaki ilerleme çubuğunu takip edebilirsiniz.</li>
        </ul>
        """
        return self._create_browser(content)

    def _create_general_tab(self):
        content = """
        <style>
            h3 { color: #8eff8e; margin-top: 20px; margin-bottom: 10px; }
            p { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            ul { color: #d4d4d4; line-height: 1.6; font-size: 14px; }
            li { margin-bottom: 10px; }
            b { color: #ffffff; }
        </style>
        <h3>Medya Kasası (Media Vault) Nedir?</h3>
        <p>Tüm fotoğraflarınızın ve veritabanı kayıtlarınızın güvenle saklandığı ana dizindir. Bu klasörü silmek veya ismini değiştirmek uygulama verilerinin kaybolmasına neden olabilir.</p>

        <h3>Veri Gizliliği</h3>
        <p><b>Tirnavali Acknowledge</b> tamamen yerel çalışacak şekilde tasarlanmıştır:</p>
        <ul>
            <li>Fotoğraflarınız hiçbir şekilde internete veya buluta gönderilmez.</li>
            <li>Yapay zeka analizleri kendi bilgisayarınızın donanımı kullanılarak yapılır.</li>
        </ul>

        <h3>Güncellemeler</h3>
        <p>Yeni özellikler ve iyileştirmeler için uygulamanızı düzenli olarak güncel tutmanız önerilir.</p>
        """
        return self._create_browser(content)

    def _create_browser(self, html_content):
        browser = QtWidgets.QTextBrowser()
        browser.setHtml(html_content)
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("background: transparent; border: none; padding: 10px;")
        return browser
