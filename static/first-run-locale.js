/* First-run locale additions. Keep this page fully aligned with the selected UI language. */
(()=>{'use strict';
const C=window.ZETALVX_LOCALES;if(!C)return;
const entries=[
  {
    "sources": [
      "Setup code for another device"
    ],
    "text": {
      "en": "Setup code for another device",
      "it": "Codice per configurare un altro dispositivo",
      "es": "Código para configurar otro dispositivo",
      "fr": "Code pour configurer un autre appareil",
      "de": "Code zum Einrichten eines weiteren Geräts",
      "pt": "Código para configurar outro dispositivo",
      "ru": "Код для настройки другого устройства",
      "zh": "用于配置其他设备的代码",
      "ja": "別のデバイスを設定するためのコード",
      "ko": "다른 기기를 설정하기 위한 코드",
      "tr": "Başka bir cihazı kurmak için kod",
      "ar": "رمز إعداد جهاز آخر"
    }
  },
  {
    "sources": [
      "Valid for 20 minutes. This local page refreshes the code automatically when it expires. SETUP-CODE.cmd can also rotate it manually."
    ],
    "text": {
      "en": "Valid for 20 minutes. This local page refreshes the code automatically when it expires. SETUP-CODE.cmd can also rotate it manually.",
      "it": "Valido per 20 minuti. Questa pagina locale aggiorna automaticamente il codice quando scade. Puoi anche rigenerarlo manualmente con SETUP-CODE.cmd.",
      "es": "Válido durante 20 minutos. Esta página local actualiza el código automáticamente cuando caduca. También puedes regenerarlo manualmente con SETUP-CODE.cmd.",
      "fr": "Valide pendant 20 minutes. Cette page locale renouvelle automatiquement le code lorsqu’il expire. Vous pouvez aussi le régénérer manuellement avec SETUP-CODE.cmd.",
      "de": "20 Minuten gültig. Diese lokale Seite erneuert den Code nach Ablauf automatisch. Du kannst ihn auch manuell mit SETUP-CODE.cmd neu erzeugen.",
      "pt": "Válido por 20 minutos. Esta página local atualiza o código automaticamente quando ele expira. Também pode regenerá-lo manualmente com SETUP-CODE.cmd.",
      "ru": "Действует 20 минут. Эта локальная страница автоматически обновляет код после истечения срока. Код также можно создать вручную через SETUP-CODE.cmd.",
      "zh": "有效期为 20 分钟。此本地页面会在代码过期后自动刷新。也可以使用 SETUP-CODE.cmd 手动重新生成。",
      "ja": "20分間有効です。このローカルページは期限切れになるとコードを自動更新します。SETUP-CODE.cmd で手動再生成することもできます。",
      "ko": "20분 동안 유효합니다. 이 로컬 페이지는 코드가 만료되면 자동으로 새로 갱신합니다. SETUP-CODE.cmd로 수동 재생성할 수도 있습니다.",
      "tr": "20 dakika geçerlidir. Bu yerel sayfa kodun süresi dolduğunda kodu otomatik olarak yeniler. SETUP-CODE.cmd ile manuel olarak da yeniden oluşturabilirsiniz.",
      "ar": "صالح لمدة 20 دقيقة. تقوم هذه الصفحة المحلية بتجديد الرمز تلقائياً عند انتهاء صلاحيته. ويمكن أيضاً إنشاء رمز جديد يدوياً باستخدام SETUP-CODE.cmd."
    }
  },
  {
    "sources": [
      "You are configuring from another device. Enter the code shown in the terminal of the computer running the app. It is valid for 20 minutes and can be used once."
    ],
    "text": {
      "en": "You are configuring from another device. Enter the code shown in the terminal of the computer running the app. It is valid for 20 minutes and can be used once.",
      "it": "Stai configurando da un altro dispositivo. Inserisci il codice mostrato nel terminale del computer che esegue l'app. È valido per 20 minuti e si usa una sola volta.",
      "es": "Estás configurando desde otro dispositivo. Introduce el código que aparece en el terminal del equipo que ejecuta la aplicación. Es válido durante 20 minutos y solo puede usarse una vez.",
      "fr": "Vous configurez depuis un autre appareil. Saisissez le code affiché dans le terminal de l'ordinateur qui exécute l'application. Il est valable 20 minutes et ne peut être utilisé qu'une fois.",
      "de": "Du richtest die App von einem anderen Gerät ein. Gib den Code ein, der im Terminal des Computers angezeigt wird, auf dem die App läuft. Er ist 20 Minuten gültig und kann einmal verwendet werden.",
      "pt": "Está a configurar a partir de outro dispositivo. Introduza o código mostrado no terminal do computador que executa a aplicação. É válido por 20 minutos e só pode ser usado uma vez.",
      "ru": "Вы выполняете настройку с другого устройства. Введите код, показанный в терминале компьютера, на котором запущено приложение. Он действует 20 минут и используется один раз.",
      "zh": "你正在从另一台设备进行配置。请输入运行此应用的电脑终端中显示的代码。代码有效期为 20 分钟，且只能使用一次。",
      "ja": "別のデバイスから設定しています。アプリを実行しているコンピューターのターミナルに表示されたコードを入力してください。コードは20分間有効で、1回だけ使用できます。",
      "ko": "다른 기기에서 설정 중입니다. 앱을 실행 중인 컴퓨터의 터미널에 표시된 코드를 입력하세요. 코드는 20분 동안 유효하며 한 번만 사용할 수 있습니다.",
      "tr": "Başka bir cihazdan kurulum yapıyorsunuz. Uygulamanın çalıştığı bilgisayarın terminalinde gösterilen kodu girin. Kod 20 dakika geçerlidir ve yalnızca bir kez kullanılabilir.",
      "ar": "أنت تقوم بالإعداد من جهاز آخر. أدخل الرمز الظاهر في طرفية الكمبيوتر الذي يشغّل التطبيق. الرمز صالح لمدة 20 دقيقة ويمكن استخدامه مرة واحدة فقط."
    }
  },
  {
    "sources": [
      "Setup code"
    ],
    "text": {
      "en": "Setup code",
      "it": "Codice di configurazione",
      "es": "Código de configuración",
      "fr": "Code de configuration",
      "de": "Einrichtungscode",
      "pt": "Código de configuração",
      "ru": "Код настройки",
      "zh": "设置代码",
      "ja": "設定コード",
      "ko": "설정 코드",
      "tr": "Kurulum kodu",
      "ar": "رمز الإعداد"
    }
  },
  {
    "sources": [
      "Code expired or terminal closed? On the host computer run"
    ],
    "text": {
      "en": "Code expired or terminal closed? On the host computer run",
      "it": "Codice scaduto o terminale chiuso? Sul computer host esegui",
      "es": "¿El código ha caducado o se cerró el terminal? En el equipo host ejecuta",
      "fr": "Code expiré ou terminal fermé ? Sur l'ordinateur hôte, exécutez",
      "de": "Code abgelaufen oder Terminal geschlossen? Führe auf dem Host-Computer Folgendes aus:",
      "pt": "Código expirado ou terminal fechado? No computador anfitrião execute",
      "ru": "Код истёк или терминал закрыт? На компьютере-хосте выполните",
      "zh": "代码已过期或终端已关闭？请在主机电脑上运行",
      "ja": "コードの期限切れ、またはターミナルを閉じましたか？ホストコンピューターで次を実行してください:",
      "ko": "코드가 만료되었거나 터미널을 닫았나요? 호스트 컴퓨터에서 다음을 실행하세요:",
      "tr": "Kodun süresi doldu veya terminal kapandı mı? Ana bilgisayarda şunu çalıştırın:",
      "ar": "هل انتهت صلاحية الرمز أو أُغلقت الطرفية؟ على الكمبيوتر المضيف شغّل"
    }
  },
  {
    "sources": [
      "(Linux) or"
    ],
    "text": {
      "en": "(Linux) or",
      "it": "(Linux) oppure",
      "es": "(Linux) o",
      "fr": "(Linux) ou",
      "de": "(Linux) oder",
      "pt": "(Linux) ou",
      "ru": "(Linux) или",
      "zh": "（Linux）或",
      "ja": "（Linux）または",
      "ko": "(Linux) 또는",
      "tr": "(Linux) veya",
      "ar": "(Linux) أو"
    }
  },
  {
    "sources": [
      "(Windows). Do not restart or reinstall the app."
    ],
    "text": {
      "en": "(Windows). Do not restart or reinstall the app.",
      "it": "(Windows). Non riavviare o reinstallare l'app.",
      "es": "(Windows). No reinicies ni reinstales la aplicación.",
      "fr": "(Windows). Ne redémarrez pas et ne réinstallez pas l'application.",
      "de": "(Windows). Starte die App nicht neu und installiere sie nicht erneut.",
      "pt": "(Windows). Não reinicie nem reinstale a aplicação.",
      "ru": "(Windows). Не перезапускайте и не переустанавливайте приложение.",
      "zh": "（Windows）。无需重启或重新安装应用。",
      "ja": "（Windows）。アプリを再起動または再インストールする必要はありません。",
      "ko": "(Windows). 앱을 다시 시작하거나 재설치하지 마세요.",
      "tr": "(Windows). Uygulamayı yeniden başlatmayın veya yeniden kurmayın.",
      "ar": "(Windows). لا تعِد تشغيل التطبيق ولا تعِد تثبيته."
    }
  },
  {
    "sources": [
      "This PC only · recommended"
    ],
    "text": {
      "en": "This PC only · recommended",
      "it": "Solo questo PC · consigliato",
      "es": "Solo este PC · recomendado",
      "fr": "Ce PC uniquement · recommandé",
      "de": "Nur dieser PC · empfohlen",
      "pt": "Apenas este PC · recomendado",
      "ru": "Только этот ПК · рекомендуется",
      "zh": "仅此电脑 · 推荐",
      "ja": "この PC のみ · 推奨",
      "ko": "이 PC만 · 권장",
      "tr": "Yalnızca bu bilgisayar · önerilen",
      "ar": "هذا الجهاز فقط · موصى به"
    }
  },
  {
    "sources": [
      "Local network (LAN) · other devices"
    ],
    "text": {
      "en": "Local network (LAN) · other devices",
      "it": "Rete locale (LAN) · altri dispositivi",
      "es": "Red local (LAN) · otros dispositivos",
      "fr": "Réseau local (LAN) · autres appareils",
      "de": "Lokales Netzwerk (LAN) · andere Geräte",
      "pt": "Rede local (LAN) · outros dispositivos",
      "ru": "Локальная сеть (LAN) · другие устройства",
      "zh": "局域网 (LAN) · 其他设备",
      "ja": "ローカルネットワーク (LAN) · 他のデバイス",
      "ko": "로컬 네트워크 (LAN) · 다른 기기",
      "tr": "Yerel ağ (LAN) · diğer cihazlar",
      "ar": "الشبكة المحلية (LAN) · أجهزة أخرى"
    }
  },
  {
    "sources": [
      "Your access choice is saved. If you change mode, it will apply on the next restart. When connecting remotely, keep LAN enabled to continue using other devices."
    ],
    "text": {
      "en": "Your access choice is saved. If you change mode, it will apply on the next restart. When connecting remotely, keep LAN enabled to continue using other devices.",
      "it": "La scelta dell'accesso viene salvata. Se cambi modalità, verrà applicata al prossimo riavvio. Quando ti colleghi da remoto, lascia LAN attiva per continuare a usare gli altri dispositivi.",
      "es": "La opción de acceso se guarda. Si cambias el modo, se aplicará en el próximo reinicio. Si te conectas de forma remota, mantén LAN activada para seguir usando otros dispositivos.",
      "fr": "Le choix d'accès est enregistré. Si vous changez de mode, il sera appliqué au prochain redémarrage. Pour un accès à distance, laissez le LAN activé afin de continuer à utiliser les autres appareils.",
      "de": "Die Zugriffsauswahl wird gespeichert. Wenn du den Modus änderst, wird er beim nächsten Neustart angewendet. Bei Remote-Zugriff LAN aktiviert lassen, damit andere Geräte verbunden bleiben können.",
      "pt": "A opção de acesso é guardada. Se mudar o modo, será aplicada no próximo reinício. Ao ligar remotamente, mantenha a LAN ativa para continuar a usar outros dispositivos.",
      "ru": "Выбранный режим доступа сохраняется. Если вы измените его, новый режим применится после следующего перезапуска. При удалённом подключении оставьте LAN включённой, чтобы продолжать использовать другие устройства.",
      "zh": "访问方式会被保存。如果更改模式，新设置将在下次重启时生效。远程连接时请保持 LAN 启用，以便继续从其他设备访问。",
      "ja": "アクセス設定は保存されます。モードを変更した場合は次回の再起動時に適用されます。別のデバイスから接続する場合は、LAN を有効のままにしてください。",
      "ko": "접근 방식은 저장됩니다. 모드를 변경하면 다음 재시작 때 적용됩니다. 다른 기기에서 원격으로 접속하려면 LAN을 계속 활성화해 두세요.",
      "tr": "Erişim seçiminiz kaydedilir. Modu değiştirirseniz bir sonraki yeniden başlatmada uygulanır. Uzaktan bağlanırken diğer cihazları kullanmaya devam etmek için LAN'ı açık tutun.",
      "ar": "يتم حفظ خيار الوصول. إذا غيّرت الوضع فسيُطبَّق عند إعادة التشغيل التالية. عند الاتصال عن بُعد اترك LAN مفعّلة لمواصلة استخدام الأجهزة الأخرى."
    }
  },
  {
    "sources": [
      "After account setup, Setup will open automatically so you can choose an SDXL checkpoint, LoRA and Identity."
    ],
    "text": {
      "en": "After account setup, Setup will open automatically so you can choose an SDXL checkpoint, LoRA and Identity.",
      "it": "Dopo la creazione dell'account si aprirà automaticamente il Setup per scegliere checkpoint SDXL, LoRA e Identity.",
      "es": "Después de crear la cuenta, se abrirá automáticamente el Setup para elegir el checkpoint SDXL, LoRA e Identity.",
      "fr": "Après la création du compte, le Setup s'ouvrira automatiquement pour choisir le checkpoint SDXL, les LoRA et Identity.",
      "de": "Nach der Kontoerstellung wird Setup automatisch geöffnet, damit du SDXL-Checkpoint, LoRA und Identity auswählen kannst.",
      "pt": "Depois de criar a conta, o Setup será aberto automaticamente para escolher o checkpoint SDXL, LoRA e Identity.",
      "ru": "После создания аккаунта Setup откроется автоматически, чтобы выбрать checkpoint SDXL, LoRA и Identity.",
      "zh": "账户创建完成后，Setup 将自动打开，以便选择 SDXL checkpoint、LoRA 和 Identity。",
      "ja": "アカウント作成後、Setup が自動的に開き、SDXL checkpoint、LoRA、Identity を選択できます。",
      "ko": "계정 설정 후 Setup이 자동으로 열려 SDXL checkpoint, LoRA 및 Identity를 선택할 수 있습니다.",
      "tr": "Hesap oluşturulduktan sonra SDXL checkpoint, LoRA ve Identity seçebilmeniz için Setup otomatik olarak açılır.",
      "ar": "بعد إنشاء الحساب سيفتح Setup تلقائياً لاختيار checkpoint ‏SDXL وLoRA وIdentity."
    }
  },
  {
    "sources": [
      "Sessione di configurazione scaduta. Ricarica la pagina e riprova."
    ],
    "text": {
      "en": "Setup session expired. Reload the page and try again.",
      "it": "Sessione di configurazione scaduta. Ricarica la pagina e riprova.",
      "es": "La sesión de configuración ha caducado. Recarga la página e inténtalo de nuevo.",
      "fr": "La session de configuration a expiré. Rechargez la page et réessayez.",
      "de": "Die Einrichtungssitzung ist abgelaufen. Lade die Seite neu und versuche es erneut.",
      "pt": "A sessão de configuração expirou. Recarregue a página e tente novamente.",
      "ru": "Сеанс настройки истёк. Перезагрузите страницу и попробуйте снова.",
      "zh": "设置会话已过期。请重新加载页面后再试。",
      "ja": "設定セッションの有効期限が切れました。ページを再読み込みしてもう一度お試しください。",
      "ko": "설정 세션이 만료되었습니다. 페이지를 새로고침한 후 다시 시도하세요.",
      "tr": "Kurulum oturumunun süresi doldu. Sayfayı yenileyip tekrar deneyin.",
      "ar": "انتهت صلاحية جلسة الإعداد. أعد تحميل الصفحة وحاول مرة أخرى."
    }
  },
  {
    "sources": [
      "Account già configurato. Usa il login."
    ],
    "text": {
      "en": "Account already configured. Use the login page.",
      "it": "Account già configurato. Usa il login.",
      "es": "La cuenta ya está configurada. Usa la página de inicio de sesión.",
      "fr": "Le compte est déjà configuré. Utilisez la page de connexion.",
      "de": "Das Konto ist bereits eingerichtet. Verwende die Anmeldeseite.",
      "pt": "A conta já está configurada. Use a página de início de sessão.",
      "ru": "Аккаунт уже настроен. Используйте страницу входа.",
      "zh": "账户已配置。请使用登录页面。",
      "ja": "アカウントはすでに設定されています。ログインページを使用してください。",
      "ko": "계정이 이미 설정되어 있습니다. 로그인 페이지를 사용하세요.",
      "tr": "Hesap zaten yapılandırılmış. Giriş sayfasını kullanın.",
      "ar": "تم إعداد الحساب بالفعل. استخدم صفحة تسجيل الدخول."
    }
  },
  {
    "sources": [
      "Codice non disponibile. Genera un nuovo codice dal computer che esegue l’app."
    ],
    "text": {
      "en": "Setup code unavailable. Generate a new code on the computer running the app.",
      "it": "Codice non disponibile. Genera un nuovo codice dal computer che esegue l'app.",
      "es": "El código de configuración no está disponible. Genera uno nuevo en el equipo que ejecuta la aplicación.",
      "fr": "Le code de configuration n'est pas disponible. Générez-en un nouveau sur l'ordinateur qui exécute l'application.",
      "de": "Der Einrichtungscode ist nicht verfügbar. Erzeuge einen neuen Code auf dem Computer, auf dem die App läuft.",
      "pt": "O código de configuração não está disponível. Gere um novo código no computador que executa a aplicação.",
      "ru": "Код настройки недоступен. Создайте новый код на компьютере, где запущено приложение.",
      "zh": "设置代码不可用。请在运行应用的电脑上生成新代码。",
      "ja": "設定コードを利用できません。アプリを実行しているコンピューターで新しいコードを生成してください。",
      "ko": "설정 코드를 사용할 수 없습니다. 앱을 실행 중인 컴퓨터에서 새 코드를 생성하세요.",
      "tr": "Kurulum kodu kullanılamıyor. Uygulamanın çalıştığı bilgisayarda yeni bir kod oluşturun.",
      "ar": "رمز الإعداد غير متاح. أنشئ رمزاً جديداً على الكمبيوتر الذي يشغّل التطبيق."
    }
  },
  {
    "sources": [
      "Codice scaduto. Genera un nuovo codice dal computer che esegue l’app."
    ],
    "text": {
      "en": "Setup code expired. Generate a new code on the computer running the app.",
      "it": "Codice scaduto. Genera un nuovo codice dal computer che esegue l'app.",
      "es": "El código de configuración ha caducado. Genera uno nuevo en el equipo que ejecuta la aplicación.",
      "fr": "Le code de configuration a expiré. Générez-en un nouveau sur l'ordinateur qui exécute l'application.",
      "de": "Der Einrichtungscode ist abgelaufen. Erzeuge einen neuen Code auf dem Computer, auf dem die App läuft.",
      "pt": "O código de configuração expirou. Gere um novo código no computador que executa a aplicação.",
      "ru": "Срок действия кода настройки истёк. Создайте новый код на компьютере, где запущено приложение.",
      "zh": "设置代码已过期。请在运行应用的电脑上生成新代码。",
      "ja": "設定コードの有効期限が切れました。アプリを実行しているコンピューターで新しいコードを生成してください。",
      "ko": "설정 코드가 만료되었습니다. 앱을 실행 중인 컴퓨터에서 새 코드를 생성하세요.",
      "tr": "Kurulum kodunun süresi doldu. Uygulamanın çalıştığı bilgisayarda yeni bir kod oluşturun.",
      "ar": "انتهت صلاحية رمز الإعداد. أنشئ رمزاً جديداً على الكمبيوتر الذي يشغّل التطبيق."
    }
  },
  {
    "sources": [
      "Troppi tentativi. Attendi un minuto e riprova."
    ],
    "text": {
      "en": "Too many attempts. Wait one minute and try again.",
      "it": "Troppi tentativi. Attendi un minuto e riprova.",
      "es": "Demasiados intentos. Espera un minuto e inténtalo de nuevo.",
      "fr": "Trop de tentatives. Attendez une minute puis réessayez.",
      "de": "Zu viele Versuche. Warte eine Minute und versuche es erneut.",
      "pt": "Demasiadas tentativas. Aguarde um minuto e tente novamente.",
      "ru": "Слишком много попыток. Подождите минуту и попробуйте снова.",
      "zh": "尝试次数过多。请等待一分钟后再试。",
      "ja": "試行回数が多すぎます。1分待ってからもう一度お試しください。",
      "ko": "시도 횟수가 너무 많습니다. 1분 후 다시 시도하세요.",
      "tr": "Çok fazla deneme. Bir dakika bekleyip tekrar deneyin.",
      "ar": "محاولات كثيرة جداً. انتظر دقيقة ثم حاول مرة أخرى."
    }
  },
  {
    "sources": [
      "Codice di configurazione non valido."
    ],
    "text": {
      "en": "Invalid setup code.",
      "it": "Codice di configurazione non valido.",
      "es": "Código de configuración no válido.",
      "fr": "Code de configuration non valide.",
      "de": "Ungültiger Einrichtungscode.",
      "pt": "Código de configuração inválido.",
      "ru": "Недействительный код настройки.",
      "zh": "设置代码无效。",
      "ja": "設定コードが無効です。",
      "ko": "설정 코드가 올바르지 않습니다.",
      "tr": "Geçersiz kurulum kodu.",
      "ar": "رمز الإعداد غير صالح."
    }
  },
  {
    "sources": [
      "Il nome utente deve avere da 1 a 80 caratteri."
    ],
    "text": {
      "en": "Username must be between 1 and 80 characters.",
      "it": "Il nome utente deve avere da 1 a 80 caratteri.",
      "es": "El nombre de usuario debe tener entre 1 y 80 caracteres.",
      "fr": "Le nom d'utilisateur doit contenir entre 1 et 80 caractères.",
      "de": "Der Benutzername muss zwischen 1 und 80 Zeichen lang sein.",
      "pt": "O nome de utilizador deve ter entre 1 e 80 caracteres.",
      "ru": "Имя пользователя должно содержать от 1 до 80 символов.",
      "zh": "用户名长度必须为 1 到 80 个字符。",
      "ja": "ユーザー名は1〜80文字で入力してください。",
      "ko": "사용자 이름은 1~80자여야 합니다.",
      "tr": "Kullanıcı adı 1 ile 80 karakter arasında olmalıdır.",
      "ar": "يجب أن يتراوح اسم المستخدم بين 1 و80 حرفاً."
    }
  },
  {
    "sources": [
      "La password deve avere da 10 a 1024 caratteri."
    ],
    "text": {
      "en": "Password must be between 10 and 1024 characters.",
      "it": "La password deve avere da 10 a 1024 caratteri.",
      "es": "La contraseña debe tener entre 10 y 1024 caracteres.",
      "fr": "Le mot de passe doit contenir entre 10 et 1024 caractères.",
      "de": "Das Passwort muss zwischen 10 und 1024 Zeichen lang sein.",
      "pt": "A palavra-passe deve ter entre 10 e 1024 caracteres.",
      "ru": "Пароль должен содержать от 10 до 1024 символов.",
      "zh": "密码长度必须为 10 到 1024 个字符。",
      "ja": "パスワードは10〜1024文字で入力してください。",
      "ko": "비밀번호는 10~1024자여야 합니다.",
      "tr": "Parola 10 ile 1024 karakter arasında olmalıdır.",
      "ar": "يجب أن تتراوح كلمة المرور بين 10 و1024 حرفاً."
    }
  },
  {
    "sources": [
      "Le password non coincidono."
    ],
    "text": {
      "en": "Passwords do not match.",
      "it": "Le password non coincidono.",
      "es": "Las contraseñas no coinciden.",
      "fr": "Les mots de passe ne correspondent pas.",
      "de": "Die Passwörter stimmen nicht überein.",
      "pt": "As palavras-passe não coincidem.",
      "ru": "Пароли не совпадают.",
      "zh": "两次输入的密码不一致。",
      "ja": "パスワードが一致しません。",
      "ko": "비밀번호가 일치하지 않습니다.",
      "tr": "Parolalar eşleşmiyor.",
      "ar": "كلمتا المرور غير متطابقتين."
    }
  },
  {
    "sources": [
      "Scegli accesso locale oppure LAN."
    ],
    "text": {
      "en": "Choose local or LAN access.",
      "it": "Scegli accesso locale oppure LAN.",
      "es": "Elige acceso local o LAN.",
      "fr": "Choisissez l'accès local ou LAN.",
      "de": "Wähle lokalen oder LAN-Zugriff.",
      "pt": "Escolha acesso local ou LAN.",
      "ru": "Выберите локальный доступ или LAN.",
      "zh": "请选择本地访问或 LAN 访问。",
      "ja": "ローカルアクセスまたは LAN アクセスを選択してください。",
      "ko": "로컬 또는 LAN 접근을 선택하세요.",
      "tr": "Yerel veya LAN erişimini seçin.",
      "ar": "اختر الوصول المحلي أو عبر LAN."
    }
  },
  {
    "sources": [
      "Impossibile salvare la configurazione. Controlla i permessi sul computer host e riprova."
    ],
    "text": {
      "en": "Could not save the configuration. Check permissions on the host computer and try again.",
      "it": "Impossibile salvare la configurazione. Controlla i permessi sul computer host e riprova.",
      "es": "No se pudo guardar la configuración. Comprueba los permisos en el equipo host e inténtalo de nuevo.",
      "fr": "Impossible d'enregistrer la configuration. Vérifiez les permissions sur l'ordinateur hôte et réessayez.",
      "de": "Die Konfiguration konnte nicht gespeichert werden. Prüfe die Berechtigungen auf dem Host-Computer und versuche es erneut.",
      "pt": "Não foi possível guardar a configuração. Verifique as permissões no computador anfitrião e tente novamente.",
      "ru": "Не удалось сохранить конфигурацию. Проверьте разрешения на компьютере-хосте и попробуйте снова.",
      "zh": "无法保存配置。请检查主机电脑上的权限后重试。",
      "ja": "設定を保存できませんでした。ホストコンピューターの権限を確認して、もう一度お試しください。",
      "ko": "구성을 저장할 수 없습니다. 호스트 컴퓨터의 권한을 확인한 후 다시 시도하세요.",
      "tr": "Yapılandırma kaydedilemedi. Ana bilgisayardaki izinleri kontrol edip tekrar deneyin.",
      "ar": "تعذر حفظ الإعدادات. تحقق من الأذونات على الكمبيوتر المضيف ثم حاول مرة أخرى."
    }
  },
  {
    "sources": [
      "Valid for 20 minutes. This local page refreshes the code automatically when it expires. creator-sdxl setup-code can also rotate it manually."
    ],
    "text": {
      "en": "Valid for 20 minutes. This local page refreshes the code automatically when it expires. creator-sdxl setup-code can also rotate it manually.",
      "it": "Valido per 20 minuti. Questa pagina locale aggiorna automaticamente il codice quando scade. Puoi anche rigenerarlo manualmente con creator-sdxl setup-code.",
      "es": "Válido durante 20 minutos. Esta página local actualiza el código automáticamente cuando caduca. También puedes regenerarlo manualmente con creator-sdxl setup-code.",
      "fr": "Valide pendant 20 minutes. Cette page locale renouvelle automatiquement le code lorsqu’il expire. Vous pouvez aussi le régénérer manuellement avec creator-sdxl setup-code.",
      "de": "20 Minuten gültig. Diese lokale Seite erneuert den Code nach Ablauf automatisch. Du kannst ihn auch manuell mit creator-sdxl setup-code neu erzeugen.",
      "pt": "Válido por 20 minutos. Esta página local atualiza o código automaticamente quando ele expira. Também pode regenerá-lo manualmente com creator-sdxl setup-code.",
      "ru": "Действует 20 минут. Эта локальная страница автоматически обновляет код после истечения срока. Код также можно создать вручную через creator-sdxl setup-code.",
      "zh": "有效期为 20 分钟。此本地页面会在代码过期后自动刷新。也可以使用 creator-sdxl setup-code 手动重新生成。",
      "ja": "20分間有効です。このローカルページは期限切れになるとコードを自動更新します。creator-sdxl setup-code で手動再生成することもできます。",
      "ko": "20분 동안 유효합니다. 이 로컬 페이지는 코드가 만료되면 자동으로 새로 갱신합니다. creator-sdxl setup-code로 수동 재생성할 수도 있습니다.",
      "tr": "20 dakika geçerlidir. Bu yerel sayfa kodun süresi dolduğunda kodu otomatik olarak yeniler. creator-sdxl setup-code ile manuel olarak da yeniden oluşturabilirsiniz.",
      "ar": "صالح لمدة 20 دقيقة. تقوم هذه الصفحة المحلية بتجديد الرمز تلقائياً عند انتهاء صلاحيته. ويمكن أيضاً إنشاء رمز جديد يدوياً باستخدام creator-sdxl setup-code."
    }
  }
];
C.entries.push(...entries);
function title(){if(window.ZI18n)document.title=window.ZI18n.t('First setup')+' · Zetalvx Image Lab — SDXL Edition'}
window.addEventListener('languagechange',title);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',title,{once:true});else setTimeout(title,0);
})();
