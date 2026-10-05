/* 1.0.8: managed GGUF runtime status in every supported UI language. */
(()=>{const C=window.ZETALVX_LOCALES;const entries=[
  {
    "sources": [
      "GGUF runtime preparation"
    ],
    "text": {
      "en": "GGUF runtime preparation",
      "it": "Preparazione runtime GGUF",
      "es": "Preparación del entorno GGUF",
      "fr": "Préparation du runtime GGUF",
      "de": "GGUF-Laufzeit vorbereiten",
      "pt": "Preparação do ambiente GGUF",
      "ru": "Подготовка среды GGUF",
      "zh": "准备 GGUF 运行环境",
      "ja": "GGUF実行環境の準備",
      "ko": "GGUF 런타임 준비",
      "tr": "GGUF çalışma ortamı hazırlanıyor",
      "ar": "تجهيز بيئة تشغيل GGUF"
    }
  },
  {
    "sources": [
      "Reading official release metadata…"
    ],
    "text": {
      "en": "Reading official release metadata…",
      "it": "Lettura delle versioni ufficiali…",
      "es": "Consultando versiones oficiales…",
      "fr": "Lecture des versions officielles…",
      "de": "Offizielle Versionsdaten werden gelesen…",
      "pt": "Consultando versões oficiais…",
      "ru": "Чтение данных официальных выпусков…",
      "zh": "正在读取官方发布信息…",
      "ja": "公式リリース情報を取得中…",
      "ko": "공식 릴리스 정보 확인 중…",
      "tr": "Resmî sürüm bilgileri okunuyor…",
      "ar": "جارٍ قراءة معلومات الإصدارات الرسمية…"
    }
  },
  {
    "sources": [
      "Selecting a compatible backend…"
    ],
    "text": {
      "en": "Selecting a compatible backend…",
      "it": "Selezione di un backend compatibile…",
      "es": "Seleccionando un backend compatible…",
      "fr": "Sélection d’un backend compatible…",
      "de": "Kompatibles Backend wird ausgewählt…",
      "pt": "Selecionando um backend compatível…",
      "ru": "Выбор совместимого бэкенда…",
      "zh": "正在选择兼容的后端…",
      "ja": "互換性のあるバックエンドを選択中…",
      "ko": "호환 백엔드 선택 중…",
      "tr": "Uyumlu arka uç seçiliyor…",
      "ar": "جارٍ اختيار محرك متوافق…"
    }
  },
  {
    "sources": [
      "Downloading the runtime…"
    ],
    "text": {
      "en": "Downloading the runtime…",
      "it": "Download del runtime…",
      "es": "Descargando el entorno…",
      "fr": "Téléchargement du runtime…",
      "de": "Laufzeit wird heruntergeladen…",
      "pt": "Baixando o ambiente…",
      "ru": "Загрузка среды выполнения…",
      "zh": "正在下载运行环境…",
      "ja": "実行環境をダウンロード中…",
      "ko": "런타임 다운로드 중…",
      "tr": "Çalışma ortamı indiriliyor…",
      "ar": "جارٍ تنزيل بيئة التشغيل…"
    }
  },
  {
    "sources": [
      "Verifying SHA-256…"
    ],
    "text": {
      "en": "Verifying SHA-256…",
      "it": "Verifica SHA-256…",
      "es": "Verificando SHA-256…",
      "fr": "Vérification SHA-256…",
      "de": "SHA-256 wird geprüft…",
      "pt": "Verificando SHA-256…",
      "ru": "Проверка SHA-256…",
      "zh": "正在验证 SHA-256…",
      "ja": "SHA-256を検証中…",
      "ko": "SHA-256 검증 중…",
      "tr": "SHA-256 doğrulanıyor…",
      "ar": "جارٍ التحقق من SHA-256…"
    }
  },
  {
    "sources": [
      "Extracting the runtime…"
    ],
    "text": {
      "en": "Extracting the runtime…",
      "it": "Estrazione del runtime…",
      "es": "Extrayendo el entorno…",
      "fr": "Extraction du runtime…",
      "de": "Laufzeit wird entpackt…",
      "pt": "Extraindo o ambiente…",
      "ru": "Распаковка среды выполнения…",
      "zh": "正在解压运行环境…",
      "ja": "実行環境を展開中…",
      "ko": "런타임 압축 해제 중…",
      "tr": "Çalışma ortamı çıkarılıyor…",
      "ar": "جارٍ فك ضغط بيئة التشغيل…"
    }
  },
  {
    "sources": [
      "Checking the upstream license…"
    ],
    "text": {
      "en": "Checking the upstream license…",
      "it": "Verifica della licenza originale…",
      "es": "Verificando la licencia original…",
      "fr": "Vérification de la licence d’origine…",
      "de": "Upstream-Lizenz wird geprüft…",
      "pt": "Verificando a licença original…",
      "ru": "Проверка лицензии исходного проекта…",
      "zh": "正在检查上游许可证…",
      "ja": "上流プロジェクトのライセンスを確認中…",
      "ko": "원본 프로젝트 라이선스 확인 중…",
      "tr": "Kaynak projenin lisansı denetleniyor…",
      "ar": "جارٍ التحقق من ترخيص المشروع الأصلي…"
    }
  },
  {
    "sources": [
      "Testing llama-server…"
    ],
    "text": {
      "en": "Testing llama-server…",
      "it": "Verifica di llama-server…",
      "es": "Probando llama-server…",
      "fr": "Test de llama-server…",
      "de": "llama-server wird getestet…",
      "pt": "Testando llama-server…",
      "ru": "Проверка llama-server…",
      "zh": "正在测试 llama-server…",
      "ja": "llama-serverをテスト中…",
      "ko": "llama-server 테스트 중…",
      "tr": "llama-server test ediliyor…",
      "ar": "جارٍ اختبار llama-server…"
    }
  },
  {
    "sources": [
      "Activating the verified runtime…"
    ],
    "text": {
      "en": "Activating the verified runtime…",
      "it": "Attivazione del runtime verificato…",
      "es": "Activando el entorno verificado…",
      "fr": "Activation du runtime vérifié…",
      "de": "Geprüfte Laufzeit wird aktiviert…",
      "pt": "Ativando o ambiente verificado…",
      "ru": "Активация проверенной среды…",
      "zh": "正在启用已验证的运行环境…",
      "ja": "検証済みの実行環境を有効化中…",
      "ko": "검증된 런타임 활성화 중…",
      "tr": "Doğrulanan çalışma ortamı etkinleştiriliyor…",
      "ar": "جارٍ تفعيل بيئة التشغيل المتحقق منها…"
    }
  },
  {
    "sources": [
      "Trying another compatible backend…"
    ],
    "text": {
      "en": "Trying another compatible backend…",
      "it": "Prova di un altro backend compatibile…",
      "es": "Probando otro backend compatible…",
      "fr": "Essai d’un autre backend compatible…",
      "de": "Ein anderes kompatibles Backend wird getestet…",
      "pt": "Testando outro backend compatível…",
      "ru": "Проверка другого совместимого бэкенда…",
      "zh": "正在尝试其他兼容后端…",
      "ja": "別の互換バックエンドを試しています…",
      "ko": "다른 호환 백엔드 시도 중…",
      "tr": "Başka bir uyumlu arka uç deneniyor…",
      "ar": "جارٍ تجربة محرك متوافق آخر…"
    }
  },
  {
    "sources": [
      "Official runtime ready"
    ],
    "text": {
      "en": "Official runtime ready",
      "it": "Runtime ufficiale pronto",
      "es": "Entorno oficial listo",
      "fr": "Runtime officiel prêt",
      "de": "Offizielle Laufzeit bereit",
      "pt": "Ambiente oficial pronto",
      "ru": "Официальная среда готова",
      "zh": "官方运行环境已就绪",
      "ja": "公式実行環境の準備完了",
      "ko": "공식 런타임 준비 완료",
      "tr": "Resmî çalışma ortamı hazır",
      "ar": "بيئة التشغيل الرسمية جاهزة"
    }
  },
  {
    "sources": [
      "GitHub access is limited or refused. Retry later."
    ],
    "text": {
      "en": "GitHub access is limited or refused. Retry later.",
      "it": "Accesso a GitHub limitato o negato. Riprova più tardi.",
      "es": "Acceso a GitHub limitado o denegado. Inténtalo más tarde.",
      "fr": "Accès à GitHub limité ou refusé. Réessayez plus tard.",
      "de": "GitHub-Zugriff begrenzt oder verweigert. Später erneut versuchen.",
      "pt": "Acesso ao GitHub limitado ou negado. Tente novamente mais tarde.",
      "ru": "Доступ к GitHub ограничен или запрещён. Повторите позже.",
      "zh": "GitHub 访问受限或被拒绝。请稍后重试。",
      "ja": "GitHubへのアクセスが制限または拒否されました。後で再試行してください。",
      "ko": "GitHub 접근이 제한되거나 거부되었습니다. 나중에 다시 시도하세요.",
      "tr": "GitHub erişimi sınırlı veya reddedildi. Daha sonra yeniden deneyin.",
      "ar": "الوصول إلى GitHub محدود أو مرفوض. أعد المحاولة لاحقًا."
    }
  },
  {
    "sources": [
      "Cannot reach GitHub. Check your connection and try again."
    ],
    "text": {
      "en": "Cannot reach GitHub. Check your connection and try again.",
      "it": "GitHub non raggiungibile. Controlla la connessione e riprova.",
      "es": "No se puede acceder a GitHub. Comprueba la conexión y reintenta.",
      "fr": "GitHub est inaccessible. Vérifiez la connexion et réessayez.",
      "de": "GitHub nicht erreichbar. Verbindung prüfen und erneut versuchen.",
      "pt": "Não foi possível acessar o GitHub. Verifique a conexão e tente novamente.",
      "ru": "Нет связи с GitHub. Проверьте соединение и повторите попытку.",
      "zh": "无法连接 GitHub。请检查网络后重试。",
      "ja": "GitHubに接続できません。接続を確認して再試行してください。",
      "ko": "GitHub에 연결할 수 없습니다. 연결을 확인하고 다시 시도하세요.",
      "tr": "GitHub’a ulaşılamıyor. Bağlantınızı kontrol edip yeniden deneyin.",
      "ar": "تعذر الاتصال بـ GitHub. تحقق من الاتصال وأعد المحاولة."
    }
  },
  {
    "sources": [
      "GitHub returned invalid release metadata."
    ],
    "text": {
      "en": "GitHub returned invalid release metadata.",
      "it": "GitHub ha restituito metadati di versione non validi.",
      "es": "GitHub devolvió metadatos de versión no válidos.",
      "fr": "GitHub a renvoyé des métadonnées de version invalides.",
      "de": "GitHub hat ungültige Versionsdaten zurückgegeben.",
      "pt": "O GitHub retornou metadados de versão inválidos.",
      "ru": "GitHub вернул некорректные данные выпуска.",
      "zh": "GitHub 返回了无效的发布信息。",
      "ja": "GitHubから無効なリリース情報が返されました。",
      "ko": "GitHub에서 잘못된 릴리스 정보를 반환했습니다.",
      "tr": "GitHub geçersiz sürüm bilgileri döndürdü.",
      "ar": "أعاد GitHub معلومات إصدار غير صالحة."
    }
  },
  {
    "sources": [
      "No published stable release was found."
    ],
    "text": {
      "en": "No published stable release was found.",
      "it": "Nessuna versione stabile pubblicata trovata.",
      "es": "No se encontró ninguna versión estable publicada.",
      "fr": "Aucune version stable publiée n’a été trouvée.",
      "de": "Keine veröffentlichte stabile Version gefunden.",
      "pt": "Nenhuma versão estável publicada foi encontrada.",
      "ru": "Опубликованный стабильный выпуск не найден.",
      "zh": "未找到已发布的稳定版本。",
      "ja": "公開された安定版が見つかりませんでした。",
      "ko": "공개된 안정 버전을 찾지 못했습니다.",
      "tr": "Yayımlanmış kararlı sürüm bulunamadı.",
      "ar": "لم يُعثر على إصدار مستقر منشور."
    }
  },
  {
    "sources": [
      "No compatible binary was found for this system."
    ],
    "text": {
      "en": "No compatible binary was found for this system.",
      "it": "Nessun binario compatibile trovato per questo sistema.",
      "es": "No se encontró un binario compatible con este sistema.",
      "fr": "Aucun binaire compatible avec ce système n’a été trouvé.",
      "de": "Keine kompatible Binärdatei für dieses System gefunden.",
      "pt": "Nenhum binário compatível com este sistema foi encontrado.",
      "ru": "Совместимый исполняемый файл для этой системы не найден.",
      "zh": "未找到适用于此系统的兼容二进制文件。",
      "ja": "このシステムに対応するバイナリが見つかりませんでした。",
      "ko": "이 시스템에 호환되는 바이너리를 찾지 못했습니다.",
      "tr": "Bu sistem için uyumlu ikili dosya bulunamadı.",
      "ar": "لم يُعثر على ملف تنفيذي متوافق مع هذا النظام."
    }
  },
  {
    "sources": [
      "No compatible backend could be started."
    ],
    "text": {
      "en": "No compatible backend could be started.",
      "it": "Impossibile avviare un backend compatibile.",
      "es": "No se pudo iniciar un backend compatible.",
      "fr": "Impossible de démarrer un backend compatible.",
      "de": "Kein kompatibles Backend konnte gestartet werden.",
      "pt": "Não foi possível iniciar um backend compatível.",
      "ru": "Не удалось запустить совместимый бэкенд.",
      "zh": "无法启动兼容的后端。",
      "ja": "互換性のあるバックエンドを起動できませんでした。",
      "ko": "호환 백엔드를 시작하지 못했습니다.",
      "tr": "Uyumlu bir arka uç başlatılamadı.",
      "ar": "تعذر بدء محرك متوافق."
    }
  },
  {
    "sources": [
      "Runtime integrity verification failed. Nothing was installed."
    ],
    "text": {
      "en": "Runtime integrity verification failed. Nothing was installed.",
      "it": "Verifica integrità del runtime fallita. Nessuna installazione eseguita.",
      "es": "Falló la verificación de integridad. No se instaló nada.",
      "fr": "Échec de la vérification d’intégrité du runtime. Rien n’a été installé.",
      "de": "Integritätsprüfung der Laufzeit fehlgeschlagen. Nichts wurde installiert.",
      "pt": "Falha na verificação de integridade do ambiente. Nada foi instalado.",
      "ru": "Проверка целостности среды не пройдена. Ничего не установлено.",
      "zh": "运行环境完整性验证失败。未安装任何内容。",
      "ja": "実行環境の整合性検証に失敗しました。何もインストールされていません。",
      "ko": "런타임 무결성 검증에 실패했습니다. 아무것도 설치되지 않았습니다.",
      "tr": "Çalışma ortamı bütünlük doğrulaması başarısız. Hiçbir şey kurulmadı.",
      "ar": "فشل التحقق من سلامة بيئة التشغيل. لم يتم تثبيت أي شيء."
    }
  },
  {
    "sources": [
      "Runtime preparation failed. See the technical log."
    ],
    "text": {
      "en": "Runtime preparation failed. See the technical log.",
      "it": "Preparazione del runtime fallita. Consulta il log tecnico.",
      "es": "Falló la preparación del entorno. Consulta el registro técnico.",
      "fr": "Échec de la préparation du runtime. Consultez le journal technique.",
      "de": "Vorbereitung der Laufzeit fehlgeschlagen. Technisches Protokoll prüfen.",
      "pt": "Falha na preparação do ambiente. Consulte o log técnico.",
      "ru": "Подготовка среды не удалась. См. технический журнал.",
      "zh": "运行环境准备失败。请查看技术日志。",
      "ja": "実行環境の準備に失敗しました。技術ログを確認してください。",
      "ko": "런타임 준비에 실패했습니다. 기술 로그를 확인하세요.",
      "tr": "Çalışma ortamı hazırlanamadı. Teknik günlüğe bakın.",
      "ar": "فشل تجهيز بيئة التشغيل. راجع السجل التقني."
    }
  },
  {
    "sources": [
      "Technical details"
    ],
    "text": {
      "en": "Technical details",
      "it": "Dettagli tecnici",
      "es": "Detalles técnicos",
      "fr": "Détails techniques",
      "de": "Technische Details",
      "pt": "Detalhes técnicos",
      "ru": "Технические сведения",
      "zh": "技术详情",
      "ja": "技術的な詳細",
      "ko": "기술 세부 정보",
      "tr": "Teknik ayrıntılar",
      "ar": "التفاصيل التقنية"
    }
  },
  {
    "sources": [
      "Runtime preparation interrupted"
    ],
    "text": {
      "en": "Runtime preparation interrupted",
      "it": "Preparazione del runtime interrotta",
      "es": "Preparación del entorno interrumpida",
      "fr": "Préparation du runtime interrompue",
      "de": "Vorbereitung der Laufzeit unterbrochen",
      "pt": "Preparação do ambiente interrompida",
      "ru": "Подготовка среды прервана",
      "zh": "运行环境准备已中断",
      "ja": "実行環境の準備が中断されました",
      "ko": "런타임 준비 중단됨",
      "tr": "Çalışma ortamı hazırlığı kesildi",
      "ar": "توقف تجهيز بيئة التشغيل"
    }
  },
  {
    "sources": [
      "No managed runtime installed. Select Prepare runtime."
    ],
    "text": {
      "en": "No managed runtime installed. Select Prepare runtime.",
      "it": "Runtime gestito non installato. Seleziona Prepara runtime.",
      "es": "No hay un entorno gestionado instalado. Selecciona Preparar entorno.",
      "fr": "Aucun runtime géré installé. Sélectionnez Préparer le runtime.",
      "de": "Keine verwaltete Laufzeit installiert. Laufzeit vorbereiten wählen.",
      "pt": "Nenhum ambiente gerenciado instalado. Selecione Preparar ambiente.",
      "ru": "Управляемая среда не установлена. Выберите «Подготовить среду».",
      "zh": "尚未安装托管运行环境。请选择“准备运行环境”。",
      "ja": "管理対象の実行環境がありません。「実行環境を準備」を選んでください。",
      "ko": "관리 런타임이 설치되지 않았습니다. 런타임 준비를 선택하세요.",
      "tr": "Yönetilen çalışma ortamı kurulu değil. Ortamı hazırla seçeneğini kullanın.",
      "ar": "لم تُثبَّت بيئة تشغيل مُدارة. اختر تجهيز بيئة التشغيل."
    }
  },
  {
    "sources": [
      "Automatic fallback"
    ],
    "text": {
      "en": "Automatic fallback",
      "it": "Backend alternativo automatico",
      "es": "Alternativa automática",
      "fr": "Solution de repli automatique",
      "de": "Automatischer Fallback",
      "pt": "Alternativa automática",
      "ru": "Автоматический переход",
      "zh": "已自动切换后端",
      "ja": "自動フォールバック",
      "ko": "자동 대체 백엔드",
      "tr": "Otomatik alternatif",
      "ar": "بديل تلقائي"
    }
  },
  {
    "sources": [
      "Cannot reach the app. Try again."
    ],
    "text": {
      "en": "Cannot reach the app. Try again.",
      "it": "Applicazione non raggiungibile. Riprova.",
      "es": "No se puede acceder a la aplicación. Reintenta.",
      "fr": "Application inaccessible. Réessayez.",
      "de": "App nicht erreichbar. Erneut versuchen.",
      "pt": "Não foi possível acessar o aplicativo. Tente novamente.",
      "ru": "Приложение недоступно. Повторите попытку.",
      "zh": "无法连接应用。请重试。",
      "ja": "アプリに接続できません。再試行してください。",
      "ko": "앱에 연결할 수 없습니다. 다시 시도하세요.",
      "tr": "Uygulamaya ulaşılamıyor. Yeniden deneyin.",
      "ar": "تعذر الاتصال بالتطبيق. أعد المحاولة."
    }
  }
];
C.entries.push(...entries);})();
