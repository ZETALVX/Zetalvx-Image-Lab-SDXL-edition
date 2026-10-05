/* Identity input roles and checkpoint labels, all supported languages. */
window.ZETALVX_LOCALES.entries.push(...[
  {
    "sources": [
      "Subject's face · required"
    ],
    "text": {
      "en": "Subject's face · required",
      "it": "Volto del soggetto · obbligatorio",
      "es": "Rostro del sujeto · obligatorio",
      "fr": "Visage du sujet · requis",
      "de": "Gesicht der Person · erforderlich",
      "pt": "Rosto do sujeito · obrigatório",
      "ru": "Лицо человека · обязательно",
      "zh": "主体面部 · 必填",
      "ja": "被写体の顔 · 必須",
      "ko": "피사체 얼굴 · 필수",
      "tr": "Kişinin yüzü · gerekli",
      "ar": "وجه الشخص · مطلوب"
    }
  },
  {
    "sources": [
      "Target image · required"
    ],
    "text": {
      "en": "Target image · required",
      "it": "Immagine da modificare · obbligatoria",
      "es": "Imagen de destino · obligatoria",
      "fr": "Image à modifier · requise",
      "de": "Zielbild · erforderlich",
      "pt": "Imagem de destino · obrigatória",
      "ru": "Целевое изображение · обязательно",
      "zh": "目标图像 · 必填",
      "ja": "変更対象の画像 · 必須",
      "ko": "대상 이미지 · 필수",
      "tr": "Hedef görüntü · gerekli",
      "ar": "الصورة المستهدفة · مطلوبة"
    }
  },
  {
    "sources": [
      "The image whose face will be replaced. The rest of the picture is kept."
    ],
    "text": {
      "en": "The image whose face will be replaced. The rest of the picture is kept.",
      "it": "La foto nella quale sostituire il volto. Il resto dell’immagine viene mantenuto.",
      "es": "La imagen cuyo rostro se sustituirá. El resto de la imagen se conserva.",
      "fr": "L’image dont le visage sera remplacé. Le reste de l’image est conservé.",
      "de": "Das Bild, in dem das Gesicht ersetzt wird. Der Rest des Bildes bleibt erhalten.",
      "pt": "A imagem cujo rosto será substituído. O restante da imagem é preservado.",
      "ru": "Изображение, на котором заменяется лицо. Остальная часть сохраняется.",
      "zh": "要替换面部的图像。图像其余部分保持不变。",
      "ja": "顔を置き換える画像です。それ以外の部分は維持されます。",
      "ko": "얼굴을 교체할 이미지입니다. 나머지 부분은 유지됩니다.",
      "tr": "Yüzü değiştirilecek görüntü. Görüntünün geri kalanı korunur.",
      "ar": "الصورة التي سيُستبدل وجهها. يُحتفظ ببقية الصورة."
    }
  },
  {
    "sources": [
      "Use a clear face photo. Only the first reference supplies the identity for Face Swap."
    ],
    "text": {
      "en": "Use a clear face photo. Only the first reference supplies the identity for Face Swap.",
      "it": "Usa una foto con il volto ben visibile. Face Swap prende l’identità solo dalla prima immagine.",
      "es": "Usa una foto con el rostro visible. Face Swap toma la identidad solo de la primera referencia.",
      "fr": "Utilisez une photo au visage net. Face Swap utilise uniquement la première référence pour l’identité.",
      "de": "Verwende ein gut sichtbares Gesicht. Face Swap übernimmt die Identität nur aus dem ersten Referenzbild.",
      "pt": "Use uma foto com o rosto nítido. Face Swap usa apenas a primeira referência para a identidade.",
      "ru": "Используйте чёткое фото лица. Face Swap берёт личность только из первого референса.",
      "zh": "使用面部清晰的照片。Face Swap 仅从第一张参考图提取身份。",
      "ja": "顔がはっきり写った写真を使います。Face Swapの顔の特徴には最初の参照画像だけが使われます。",
      "ko": "얼굴이 선명한 사진을 사용하세요. Face Swap은 첫 번째 참조에서만 얼굴 특징을 가져옵니다.",
      "tr": "Net bir yüz fotoğrafı kullanın. Face Swap kimliği yalnızca ilk referanstan alır.",
      "ar": "استخدم صورة واضحة للوجه. يأخذ Face Swap الهوية من المرجع الأول فقط."
    }
  },
  {
    "sources": [
      "Face pose · optional"
    ],
    "text": {
      "en": "Face pose · optional",
      "it": "Posa del volto · facoltativa",
      "es": "Pose del rostro · opcional",
      "fr": "Pose du visage · facultative",
      "de": "Gesichtshaltung · optional",
      "pt": "Pose do rosto · opcional",
      "ru": "Положение лица · необязательно",
      "zh": "面部姿态 · 可选",
      "ja": "顔のポーズ · 任意",
      "ko": "얼굴 포즈 · 선택",
      "tr": "Yüz pozu · isteğe bağlı",
      "ar": "وضعية الوجه · اختيارية"
    }
  },
  {
    "sources": [
      "Face landmarks only, not identity or full-body pose. Overrides the base image; without either, landmarks come from the primary face reference."
    ],
    "text": {
      "en": "Face landmarks only, not identity or full-body pose. Overrides the base image; without either, landmarks come from the primary face reference.",
      "it": "Solo punti del volto, non identità o posa del corpo. Ha priorità sulla base; senza entrambe, usa i punti del volto di riferimento.",
      "es": "Solo puntos faciales, no identidad ni pose corporal. Tiene prioridad sobre la base; sin ambas, usa los puntos del rostro de referencia principal.",
      "fr": "Points du visage uniquement, pas l’identité ni la pose du corps. Prioritaire sur la base ; sans les deux, utilise le visage de référence principal.",
      "de": "Nur Gesichtspunkte, nicht Identität oder Körperpose. Hat Vorrang vor dem Basisbild; fehlen beide, liefert das erste Referenzgesicht die Punkte.",
      "pt": "Apenas pontos faciais, não identidade ou pose corporal. Tem prioridade sobre a base; sem ambas, usa os pontos do rosto de referência principal.",
      "ru": "Только точки лица, не личность и не поза тела. Приоритет над базовым изображением; без обоих используются точки первого референса лица.",
      "zh": "仅提供面部关键点，不提供身份或全身姿态。优先于基础图像；两者都未提供时，使用第一张面部参考图的关键点。",
      "ja": "顔の特徴点のみを指定します。顔の特徴や全身ポーズは指定しません。元画像より優先され、両方なければ最初の顔参照を使います。",
      "ko": "얼굴 랜드마크만 지정하며, 얼굴 특징이나 전신 포즈는 지정하지 않습니다. 기본 이미지보다 우선하며, 둘 다 없으면 첫 얼굴 참조를 사용합니다.",
      "tr": "Yalnızca yüz noktaları; kimlik veya vücut pozu değil. Temel görüntüden önceliklidir; ikisi de yoksa ilk yüz referansının noktaları kullanılır.",
      "ar": "نقاط الوجه فقط، لا الهوية أو وضعية الجسم. له أولوية على الصورة الأساسية؛ عند غياب كليهما تُستخدم نقاط مرجع الوجه الأول."
    }
  },
  {
    "sources": [
      "Starting image · required for Img2Img"
    ],
    "text": {
      "en": "Starting image · required for Img2Img",
      "it": "Immagine di partenza · obbligatoria per Img2Img",
      "es": "Imagen inicial · obligatoria para Img2Img",
      "fr": "Image de départ · requise pour Img2Img",
      "de": "Ausgangsbild · für Img2Img erforderlich",
      "pt": "Imagem inicial · obrigatória para Img2Img",
      "ru": "Исходное изображение · обязательно для Img2Img",
      "zh": "起始图像 · Img2Img 必填",
      "ja": "元画像 · Img2Imgで必須",
      "ko": "시작 이미지 · Img2Img 필수",
      "tr": "Başlangıç görüntüsü · Img2Img için gerekli",
      "ar": "صورة البداية · مطلوبة لـ Img2Img"
    }
  },
  {
    "sources": [
      "Fallback face pose · optional"
    ],
    "text": {
      "en": "Fallback face pose · optional",
      "it": "Posa del volto alternativa · facoltativa",
      "es": "Pose facial alternativa · opcional",
      "fr": "Pose du visage de secours · facultative",
      "de": "Ersatz-Gesichtshaltung · optional",
      "pt": "Pose facial alternativa · opcional",
      "ru": "Запасное положение лица · необязательно",
      "zh": "备用面部姿态 · 可选",
      "ja": "代替の顔ポーズ · 任意",
      "ko": "대체 얼굴 포즈 · 선택",
      "tr": "Yedek yüz pozu · isteğe bağlı",
      "ar": "وضعية وجه بديلة · اختيارية"
    }
  },
  {
    "sources": [
      "Starting image for Img2Img; Denoise controls how much it changes. Also supplies face landmarks if no separate pose is provided."
    ],
    "text": {
      "en": "Starting image for Img2Img; Denoise controls how much it changes. Also supplies face landmarks if no separate pose is provided.",
      "it": "Base di Img2Img: Denoise regola quanto cambia. Fornisce anche i punti del volto se non carichi una posa separata.",
      "es": "Base de Img2Img: Denoise controla cuánto cambia. También aporta puntos faciales si no hay una pose separada.",
      "fr": "Base d’Img2Img : Denoise règle l’ampleur des changements. Fournit aussi les points du visage sans pose séparée.",
      "de": "Ausgangsbild für Img2Img; Denoise bestimmt die Änderungsstärke. Liefert auch Gesichtspunkte, wenn kein separates Posebild vorhanden ist.",
      "pt": "Base do Img2Img: Denoise controla quanto muda. Também fornece pontos faciais se não houver uma pose separada.",
      "ru": "Основа для Img2Img; Denoise задаёт степень изменений. Также даёт точки лица, если отдельная поза не указана.",
      "zh": "Img2Img 的起始图像；Denoise 控制变化幅度。没有单独的姿态图时，也提供面部关键点。",
      "ja": "Img2Imgの元画像です。Denoiseで変更量を調整します。別のポーズ画像がない場合は顔の特徴点も提供します。",
      "ko": "Img2Img 시작 이미지입니다. Denoise가 변경 정도를 조절합니다. 별도 포즈가 없으면 얼굴 랜드마크도 제공합니다.",
      "tr": "Img2Img başlangıç görüntüsü; Denoise değişim miktarını belirler. Ayrı poz yoksa yüz noktalarını da sağlar.",
      "ar": "صورة البداية لـ Img2Img؛ يحدد Denoise مقدار التغيير. توفّر أيضًا نقاط الوجه عند عدم تحديد وضعية منفصلة."
    }
  },
  {
    "sources": [
      "Used only for face landmarks when the separate pose is empty. Its background and details are not copied in text-to-image mode."
    ],
    "text": {
      "en": "Used only for face landmarks when the separate pose is empty. Its background and details are not copied in text-to-image mode.",
      "it": "Fornisce solo i punti del volto se manca la posa separata. In modalità testo non ne vengono copiati sfondo e dettagli.",
      "es": "Aporta solo puntos faciales si no hay pose separada. En modo texto a imagen no se copian su fondo ni sus detalles.",
      "fr": "Fournit seulement les points du visage sans pose séparée. En texte vers image, son fond et ses détails ne sont pas copiés.",
      "de": "Liefert nur Gesichtspunkte, wenn kein separates Posebild vorliegt. Im Text-zu-Bild-Modus werden Hintergrund und Details nicht übernommen.",
      "pt": "Fornece apenas pontos faciais se não houver pose separada. No modo texto para imagem, fundo e detalhes não são copiados.",
      "ru": "Даёт только точки лица, если нет отдельной позы. В режиме текст-в-изображение фон и детали не копируются.",
      "zh": "仅在没有单独姿态图时提供面部关键点。文生图模式不会复制其背景或细节。",
      "ja": "別のポーズ画像がない場合に顔の特徴点だけを提供します。テキストからの生成では背景や細部はコピーされません。",
      "ko": "별도 포즈가 없을 때 얼굴 랜드마크만 제공합니다. 텍스트 생성 모드에서는 배경이나 세부 요소가 복사되지 않습니다.",
      "tr": "Ayrı poz yoksa yalnızca yüz noktaları için kullanılır. Metinden görüntü modunda arka planı ve ayrıntıları kopyalanmaz.",
      "ar": "تُستخدم لنقاط الوجه فقط عند غياب الوضعية المنفصلة. لا تُنسخ خلفيتها وتفاصيلها في وضع التوليد من النص."
    }
  },
  {
    "sources": [
      "Use a clear face photo. The first reference defines the identity; additional references are diagnostic only."
    ],
    "text": {
      "en": "Use a clear face photo. The first reference defines the identity; additional references are diagnostic only.",
      "it": "Usa un volto ben visibile. La prima immagine definisce l’identità; le altre sono solo diagnostiche.",
      "es": "Usa un rostro bien visible. La primera referencia define la identidad; las demás son solo diagnósticas.",
      "fr": "Utilisez un visage net. La première référence définit l’identité ; les autres servent uniquement au diagnostic.",
      "de": "Verwende ein gut sichtbares Gesicht. Das erste Referenzbild bestimmt die Identität; weitere dienen nur der Diagnose.",
      "pt": "Use um rosto nítido. A primeira referência define a identidade; as demais servem apenas para diagnóstico.",
      "ru": "Используйте чёткое лицо. Первый референс задаёт личность; остальные используются только для диагностики.",
      "zh": "使用面部清晰的照片。第一张参考图决定身份，其余参考图仅用于诊断。",
      "ja": "顔がはっきり写った写真を使います。最初の参照画像が顔の特徴を決め、追加画像は診断にのみ使用されます。",
      "ko": "얼굴이 선명한 사진을 사용하세요. 첫 참조가 얼굴 특징을 결정하며 추가 참조는 진단에만 사용됩니다.",
      "tr": "Net bir yüz fotoğrafı kullanın. İlk referans kimliği belirler; ek referanslar yalnızca tanılama içindir.",
      "ar": "استخدم صورة واضحة للوجه. يحدد المرجع الأول الهوية؛ المراجع الإضافية للتشخيص فقط."
    }
  },
  {
    "sources": [
      "Add a starting image for Img2Img."
    ],
    "text": {
      "en": "Add a starting image for Img2Img.",
      "it": "Aggiungi l’immagine di partenza per Img2Img.",
      "es": "Añade la imagen inicial para Img2Img.",
      "fr": "Ajoutez l’image de départ pour Img2Img.",
      "de": "Füge ein Ausgangsbild für Img2Img hinzu.",
      "pt": "Adicione a imagem inicial para Img2Img.",
      "ru": "Добавьте исходное изображение для Img2Img.",
      "zh": "请添加 Img2Img 起始图像。",
      "ja": "Img2Imgの元画像を追加してください。",
      "ko": "Img2Img 시작 이미지를 추가하세요.",
      "tr": "Img2Img için bir başlangıç görüntüsü ekleyin.",
      "ar": "أضف صورة البداية لـ Img2Img."
    }
  },
  {
    "sources": [
      "Optional: fallback face landmarks."
    ],
    "text": {
      "en": "Optional: fallback face landmarks.",
      "it": "Facoltativa: punti del volto alternativi.",
      "es": "Opcional: puntos faciales alternativos.",
      "fr": "Facultatif : points du visage de secours.",
      "de": "Optional: Ersatz-Gesichtspunkte.",
      "pt": "Opcional: pontos faciais alternativos.",
      "ru": "Необязательно: запасные точки лица.",
      "zh": "可选：备用面部关键点。",
      "ja": "任意：代替の顔特徴点。",
      "ko": "선택: 대체 얼굴 랜드마크.",
      "tr": "İsteğe bağlı: yedek yüz noktaları.",
      "ar": "اختياري: نقاط وجه بديلة."
    }
  },
  {
    "sources": [
      "Optional: separate face landmarks take priority over the base image."
    ],
    "text": {
      "en": "Optional: separate face landmarks take priority over the base image.",
      "it": "Facoltativa: i punti del volto separati hanno priorità sulla base.",
      "es": "Opcional: los puntos faciales separados tienen prioridad sobre la base.",
      "fr": "Facultatif : les points du visage séparés sont prioritaires sur la base.",
      "de": "Optional: Separate Gesichtspunkte haben Vorrang vor dem Basisbild.",
      "pt": "Opcional: os pontos faciais separados têm prioridade sobre a base.",
      "ru": "Необязательно: отдельные точки лица имеют приоритет над базовым изображением.",
      "zh": "可选：单独的面部关键点优先于基础图像。",
      "ja": "任意：別の顔特徴点は元画像より優先されます。",
      "ko": "선택: 별도 얼굴 랜드마크는 기본 이미지보다 우선합니다.",
      "tr": "İsteğe bağlı: ayrı yüz noktaları temel görüntüden önceliklidir.",
      "ar": "اختياري: نقاط الوجه المنفصلة لها أولوية على الصورة الأساسية."
    }
  },
  {
    "sources": [
      "Configured default"
    ],
    "text": {
      "en": "Configured default",
      "it": "Predefinito configurato",
      "es": "Predeterminado configurado",
      "fr": "Par défaut configuré",
      "de": "Konfigurierter Standard",
      "pt": "Padrão configurado",
      "ru": "Настроено по умолчанию",
      "zh": "已配置默认项",
      "ja": "設定済みの既定値",
      "ko": "설정된 기본값",
      "tr": "Yapılandırılmış varsayılan",
      "ar": "الافتراضي المحدد"
    }
  },
  {
    "sources": [
      "Not in the current catalog"
    ],
    "text": {
      "en": "Not in the current catalog",
      "it": "Non presente nel catalogo attuale",
      "es": "No está en el catálogo actual",
      "fr": "Absent du catalogue actuel",
      "de": "Nicht im aktuellen Katalog",
      "pt": "Ausente do catálogo atual",
      "ru": "Нет в текущем каталоге",
      "zh": "不在当前目录中",
      "ja": "現在の一覧にありません",
      "ko": "현재 목록에 없음",
      "tr": "Geçerli katalogda yok",
      "ar": "غير موجود في القائمة الحالية"
    }
  },
  {
    "sources": [
      "Choose an available SDXL checkpoint. This choice does not change the default in Models."
    ],
    "text": {
      "en": "Choose an available SDXL checkpoint. This choice does not change the default in Models.",
      "it": "Scegli un checkpoint SDXL disponibile. La scelta non modifica il predefinito in Modelli.",
      "es": "Elige un checkpoint SDXL disponible. Esta selección no cambia el predeterminado en Modelos.",
      "fr": "Choisissez un checkpoint SDXL disponible. Ce choix ne modifie pas le défaut dans Modèles.",
      "de": "Wähle einen verfügbaren SDXL-Checkpoint. Die Auswahl ändert nicht den Standard unter Modelle.",
      "pt": "Escolha um checkpoint SDXL disponível. A seleção não altera o padrão em Modelos.",
      "ru": "Выберите доступный checkpoint SDXL. Выбор не меняет настройку по умолчанию в разделе «Модели».",
      "zh": "选择可用的 SDXL 检查点。此选择不会更改“模型”中的默认设置。",
      "ja": "利用可能なSDXLチェックポイントを選びます。「モデル」の既定値は変更されません。",
      "ko": "사용 가능한 SDXL 체크포인트를 선택하세요. 모델 페이지의 기본값은 변경되지 않습니다.",
      "tr": "Kullanılabilir bir SDXL checkpoint seçin. Bu seçim Modeller bölümündeki varsayılanı değiştirmez.",
      "ar": "اختر checkpoint متاحًا لـ SDXL. لا يغيّر هذا الاختيار الافتراضي في صفحة النماذج."
    }
  }
]);
