#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "LoaderModule"
    description = "Module Manager"
    version = "3.0.0"
    tags = ["system"]


import asyncio
import logging
from pathlib import Path
from typing import Any

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator


from mxc.exceptions import UsageError
from mxc import utils
from mxc.types import EmojiButton
from ..core import utils as cutils
from mxc.utils.keyboard import EmojiKeyBoard
from .. import loader
from ..core.langs import Locales


class Strings(BaseModel):
    downloading: str
    fetching: str
    repo_not_found: str
    search_empty: str
    done: str
    error: str
    reloading: str
    reloaded: str
    unloaded: str
    search_header: str
    search_item: str
    confirm_unsafe: str
    confirm_unsafe_url: str
    security_summary: str
    security_declined: str
    repo_confirm: str
    confirm_cancelled: str
    dev_usage: str
    no_args: str
    repo_added: str
    repo_removed: str
    invalid_file: str


locales = Locales(
    ru=Strings(
        downloading="⏳ | <b>Скачивание...</b>",
        fetching="⏳ | <b>Обработка <code>{id}</code>...</b>",
        repo_not_found="❌ | <b>Модуль <code>{id}</code> не найден в репозиториях.</b>",
        search_empty="❌ | <b>Модули не найдены по запросу: <code>{query}</code>.</b>",
        done="✅ | <b>Модуль <code>{name}</code> успешно загружен!</b>",
        error="❌ | <b>Ошибка: <code>{err}</code></b>",
        reloading="⏳ | <b>Перезагрузка всех модулей...</b>",
        reloaded="♻️ | <b>Модули перезагружены. Всего: {count}</b>",
        unloaded="✅ | <b>Модуль <code>{name}</code> выгружен.</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>ПРЕДУПРЕЖДЕНИЕ БЕЗОПАСНОСТИ</b><br>Вы устанавливаете модуль из <b>{source}</b> — <b>НЕПРОВЕРЕННЫЙ</b> источник.<br>Этот модуль <b>НЕ</b> был проверен и может содержать вредоносный код.<br><br><b>Вы подтверждаете установку этого модуля?</b>",
        confirm_unsafe_url="⚠️ | <b>НЕСИСТЕМНЫЙ МОДУЛЬ</b><br>Вы устанавливаете модуль <b>НЕ</b> из системного репозитория.<br><br>🔗 <b>Ссылка:</b> <code>{url}</code><br><br>Проверьте код модуля перед установкой.<br><br><b>Установить модуль?</b>",
        security_summary="<b>🔒 | БЕЗОПАСНОСТЬ КОМЬЮНИТИ-МОДУЛЕЙ</b><br><br>"
            "Вы устанавливаете модуль из <b>НЕСИСТЕМНОГО</b> источника. "
            "Напоминаем:<br><br>"
            "⬥ Вы <b>САМИ</b> несёте ответственность за установку сторонних модулей.<br>"
            "⬥ Ядро <b>НЕ</b> запускает модули в изолированной среде (sandbox).<br>"
            "⬥ Проверяйте код на: ссылки на неизвестные сайты, обфускацию, скрытые команды.<br>"
            "⬥ Системный репозиторий считается доверенным — все модули там проходят ревью.<br><br>"
            "<b>ВЫ СОГЛАСНЫ ПРОДОЛЖИТЬ?</b>",
        security_declined="❌ | <b>Установка отменена.</b> Рекомендуем использовать <b>системный репозиторий</b> — все модули там проверены.<br><br>Поиск: <code>.msearch &lt;запрос&gt;</code>",
        repo_confirm="⚠️ | <b>НЕДОВЕРЕННЫЙ ИСТОЧНИК</b><br>Вы добавляете репозиторий <code>{url}</code> — это <b>НЕ</b> системный репозиторий.<br><br>Модули из этого источника не проверяются и могут быть опасными.<br><br><b>Вы согласны добавить этот репозиторий?</b>",
        confirm_cancelled="❌ | <b>Установка отменена пользователем.</b>",
        dev_usage="❌ | <b>Прямые ссылки/файлы требуют префикса <code>dev</code>.</b>",
        no_args="❌ | <b>Укажите ID модуля, URL или ответьте на .py файл!</b>",
        repo_added="✅ | <b>Репозиторий добавлен: <code>{url}</code></b>",
        repo_removed="✅ | <b>Репозиторий удалён.</b>",
        invalid_file="❌ | <b>ТОЛЬКО .PY И .ZIP ФАЙЛЫ ПРИНИМАЮТСЯ!</b>",
    ),
    en=Strings(
        downloading="⏳ | <b>Downloading...</b>",
        fetching="⏳ | <b>Processing <code>{id}</code>...</b>",
        repo_not_found="❌ | <b>Module <code>{id}</code> not found in any repository.</b>",
        search_empty="❌ | <b>No modules found for query: <code>{query}</code>.</b>",
        done="✅ | <b>Module <code>{name}</code> loaded successfully!</b>",
        error="❌ | <b>Error: <code>{err}</code></b>",
        reloading="⏳ | <b>Reloading all modules...</b>",
        reloaded="♻️ | <b>Modules reloaded. Total: {count}</b>",
        unloaded="✅ | <b>Module <code>{name}</code> unloaded.</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>SECURITY WARNING</b><br>You are installing a module from <b>{source}</b> — an <b>UNVERIFIED</b> source.<br>This module has <b>NOT</b> been reviewed and may contain malicious code.<br><br><b>Do you confirm that you want to install this module?</b>",
        confirm_unsafe_url="⚠️ | <b>NON-SYSTEM MODULE</b><br>You are installing a module from a <b>NON-SYSTEM</b> repository.<br><br>🔗 <b>URL:</b> <code>{url}</code><br><br>Please review the module code before installing.<br><br><b>Install this module?</b>",
        security_summary="<b>🔒 | COMMUNITY MODULE SECURITY</b><br><br>"
            "You are installing a module from a <b>NON-SYSTEM</b> source. "
            "Please note:<br><br>"
            "⬥ <b>YOU</b> are responsible for installing third-party modules.<br>"
            "⬥ The core does <b>NOT</b> run modules in an isolated sandbox.<br>"
            "⬥ Check code for: unknown links, obfuscation, hidden commands.<br>"
            "⬥ The system repository is trusted — all modules there are reviewed.<br><br>"
            "<b>DO YOU AGREE TO CONTINUE?</b>",
        security_declined="❌ | <b>Installation cancelled.</b> We recommend using the <b>system repository</b> — all modules there are reviewed.<br><br>Search: <code>.msearch &lt;query&gt;</code>",
        repo_confirm="⚠️ | <b>UNTRUSTED SOURCE</b><br>You are adding repository <code>{url}</code> — this is <b>NOT</b> the system repository.<br><br>Modules from this source are not reviewed and may be dangerous.<br><br><b>Do you agree to add this repository?</b>",
        confirm_cancelled="❌ | <b>Installation cancelled by user.</b>",
        dev_usage="❌ | <b>Direct links/files require <code>dev</code> prefix.</b>",
        no_args="❌ | <b>Provide Module ID, URL or reply to a .py file!</b>",
        repo_added="✅ | <b>Repository added: <code>{url}</code></b>",
        repo_removed="✅ | <b>Repository removed.</b>",
        invalid_file="❌ | <b>ONLY .PY AND .ZIP FILES ACCEPTED!</b>",
    ),
    ua=Strings(
        downloading="⏳ | <b>Завантаження...</b>",
        fetching="⏳ | <b>Обробка <code>{id}</code>...</b>",
        repo_not_found="❌ | <b>Модуль <code>{id}</code> не знайдено в репозиторіях.</b>",
        search_empty="❌ | <b>Модулі не знайдено за запитом: <code>{query}</code>.</b>",
        done="✅ | <b>Модуль <code>{name}</code> успішно завантажено!</b>",
        error="❌ | <b>Помилка: <code>{err}</code></b>",
        reloading="⏳ | <b>Перезавантаження всіх модулів...</b>",
        reloaded="♻️ | <b>Модулі перезавантажено. Всього: {count}</b>",
        unloaded="✅ | <b>Модуль <code>{name}</code> вивантажено.</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>ПОПЕРЕДЖЕННЯ БЕЗПЕКИ</b><br>Ви встановлюєте модуль із <b>{source}</b> — <b>НЕПЕРЕВІРЕНЕ</b> джерело.<br>Цей модуль <b>НЕ</b> було перевірено та може містити шкідливий код.<br><br><b>Ви підтверджуєте встановлення цього модуля?</b>",
        confirm_unsafe_url="⚠️ | <b>НЕСИСТЕМНИЙ МОДУЛЬ</b><br>Ви встановлюєте модуль <b>НЕ</b> із системного репозиторію.<br><br>🔗 <b>Посилання:</b> <code>{url}</code><br><br>Перевірте код модуля перед встановленням.<br><br><b>Встановити модуль?</b>",
        security_summary="<b>🔒 | БЕЗПЕКА КОМ'ЮНІТІ-МОДУЛІВ</b><br><br>"
            "Ви встановлюєте модуль із <b>НЕСИСТЕМНОГО</b> джерела. "
            "Нагадуємо:<br><br>"
            "⬥ Ви <b>САМІ</b> несете відповідальність за встановлення сторонніх модулів.<br>"
            "⬥ Ядро <b>НЕ</b> запускає модулі в ізольованому середовищі (sandbox).<br>"
            "⬥ Перевіряйте код на: невідомі посилання, обфускацію, приховані команди.<br>"
            "⬥ Системний репозиторій вважається довіреним — всі модулі там проходять рев'ю.<br><br>"
            "<b>ВИ ПОГОДЖУЄТЕСЯ ПРОДОВЖИТИ?</b>",
        security_declined="❌ | <b>Встановлення скасовано.</b> Рекомендуємо використовувати <b>системний репозиторій</b> — всі модулі там перевірені.<br><br>Пошук: <code>.msearch &lt;запит&gt;</code>",
        repo_confirm="⚠️ | <b>НЕДОВІРЕНЕ ДЖЕРЕЛО</b><br>Ви додаєте репозиторій <code>{url}</code> — це <b>НЕ</b> системний репозиторій.<br><br>Модулі з цього джерела не перевіряються та можуть бути небезпечними.<br><br><b>Ви згодні додати цей репозиторій?</b>",
        confirm_cancelled="❌ | <b>Встановлення скасовано користувачем.</b>",
        dev_usage="❌ | <b>Прямі посилання/файли вимагають префікса <code>dev</code>.</b>",
        no_args="❌ | <b>Вкажіть ID модуля, URL або відповідайте на .py файл!</b>",
        repo_added="✅ | <b>Репозиторій додано: <code>{url}</code></b>",
        repo_removed="✅ | <b>Репозиторій видалено.</b>",
        invalid_file="❌ | <b>ТІЛЬКИ .PY ТА .ZIP ФАЙЛИ ПРИЙМАЮТЬСЯ!</b>",
    ),
    fr=Strings(
        downloading="⏳ | <b>Téléchargement...</b>",
        fetching="⏳ | <b>Traitement de <code>{id}</code>...</b>",
        repo_not_found="❌ | <b>Module <code>{id}</code> introuvable dans les dépôts.</b>",
        search_empty="❌ | <b>Aucun module trouvé pour la requête: <code>{query}</code>.</b>",
        done="✅ | <b>Module <code>{name}</code> chargé avec succès!</b>",
        error="❌ | <b>Erreur: <code>{err}</code></b>",
        reloading="⏳ | <b>Rechargement de tous les modules...</b>",
        reloaded="♻️ | <b>Modules rechargés. Total: {count}</b>",
        unloaded="✅ | <b>Module <code>{name}</code> déchargé.</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>AVERTISSEMENT DE SÉCURITÉ</b><br>Vous installez un module depuis <b>{source}</b> — une source <b>NON VÉRIFIÉE</b>.<br>Ce module <b>N'A PAS</b> été examiné et peut contenir du code malveillant.<br><br><b>Confirmez-vous l'installation de ce module?</b>",
        confirm_unsafe_url="⚠️ | <b>MODULE NON-SYSTÈME</b><br>Vous installez un module depuis un dépôt <b>NON SYSTÈME</b>.<br><br>🔗 <b>Lien:</b> <code>{url}</code><br><br>Vérifiez le code du module avant l'installation.<br><br><b>Installer ce module?</b>",
        security_summary="<b>🔒 | SÉCURITÉ DES MODULES COMMUNAUTAIRES</b><br><br>"
            "Vous installez un module depuis une source <b>NON SYSTÈME</b>. "
            "Rappel:<br><br>"
            "⬥ Vous êtes <b>RESPONSABLE</b> de l'installation de modules tiers.<br>"
            "⬥ Le noyau <b>NE</b> lance PAS les modules dans un sandbox isolé.<br>"
            "⬥ Vérifiez le code pour: liens inconnus, obfuscation, commandes cachées.<br>"
            "⬥ Le dépôt système est de confiance — tous les modules y sont révisés.<br><br>"
            "<b>ACCEPTEZ-VOUS DE CONTINUER?</b>",
        security_declined="❌ | <b>Installation annulée.</b> Nous recommandons d'utiliser le <b>dépôt système</b> — tous les modules y sont vérifiés.<br><br>Recherche: <code>.msearch &lt;requête&gt;</code>",
        repo_confirm="⚠️ | <b>SOURCE NON CONFIABLE</b><br>Vous ajoutez le dépôt <code>{url}</code> — ce n'est <b>PAS</b> le dépôt système.<br><br>Les modules de cette source ne sont pas vérifiés et peuvent être dangereux.<br><br><b>Acceptez-vous d'ajouter ce dépôt?</b>",
        confirm_cancelled="❌ | <b>Installation annulée par l'utilisateur.</b>",
        dev_usage="❌ | <b>Les liens/fichiers directs nécessitent le préfixe <code>dev</code>.</b>",
        no_args="❌ | <b>Fournissez un ID de module, une URL ou répondez à un fichier .py!</b>",
        repo_added="✅ | <b>Dépôt ajouté: <code>{url}</code></b>",
        repo_removed="✅ | <b>Dépôt supprimé.</b>",
        invalid_file="❌ | <b>SEULS LES FICHIERS .PY ET .ZIP SONT ACCEPTÉS!</b>",
    ),
    de=Strings(
        downloading="⏳ | <b>Herunterladen...</b>",
        fetching="⏳ | <b>Verarbeite <code>{id}</code>...</b>",
        repo_not_found="❌ | <b>Modul <code>{id}</code> in keinem Repository gefunden.</b>",
        search_empty="❌ | <b>Keine Module gefunden für: <code>{query}</code>.</b>",
        done="✅ | <b>Modul <code>{name}</code> erfolgreich geladen!</b>",
        error="❌ | <b>Fehler: <code>{err}</code></b>",
        reloading="⏳ | <b>Lade alle Module neu...</b>",
        reloaded="♻️ | <b>Module neu geladen. Gesamt: {count}</b>",
        unloaded="✅ | <b>Modul <code>{name}</code> entladen.</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>SICHERHEITSWARNUNG</b><br>Sie installieren ein Modul von <b>{source}</b> — einer <b>UNVERIFIZIERTEN</b> Quelle.<br>Dieses Modul wurde <b>NICHT</b> geprüft und könnte schädlichen Code enthalten.<br><br><b>Bestätigen Sie die Installation dieses Moduls?</b>",
        confirm_unsafe_url="⚠️ | <b>NICHT-SYSTEM-MODUL</b><br>Sie installieren ein Modul <b>NICHT</b> aus dem System-Repository.<br><br>🔗 <b>Link:</b> <code>{url}</code><br><br>Überprüfen Sie den Code vor der Installation.<br><br><b>Dieses Modul installieren?</b>",
        security_summary="<b>🔒 | SICHERHEIT VON COMMUNITY-MODULEN</b><br><br>"
            "Sie installieren ein Modul aus einer <b>NICHT-SYSTEM</b> Quelle. "
            "Hinweis:<br><br>"
            "⬥ <b>SIE</b> sind verantwortlich für die Installation von Drittanbieter-Modulen.<br>"
            "⬥ Der Kern führt Module <b>NICHT</b> in einer isolierten Sandbox aus.<br>"
            "⬥ Prüfen Sie den Code auf: unbekannte Links, Verschleierung, versteckte Befehle.<br>"
            "⬥ Das System-Repository ist vertrauenswürdig — alle Module werden dort geprüft.<br><br>"
            "<b>STIMMEN SIE ZU, FORTZUFAHREN?</b>",
        security_declined="❌ | <b>Installation abgebrochen.</b> Wir empfehlen die Nutzung des <b>System-Repository</b> — alle Module dort sind geprüft.<br><br>Suche: <code>.msearch &lt;Anfrage&gt;</code>",
        repo_confirm="⚠️ | <b>UNGESICHERTE QUELLE</b><br>Sie fügen Repository <code>{url}</code> hinzu — dies ist <b>NICHT</b> das System-Repository.<br><br>Module aus dieser Quelle sind nicht geprüft und können gefährlich sein.<br><br><b>Stimmen Sie der Hinzufügung zu?</b>",
        confirm_cancelled="❌ | <b>Installation vom Benutzer abgebrochen.</b>",
        dev_usage="❌ | <b>Direkte Links/Dateien erfordern das <code>dev</code>-Präfix.</b>",
        no_args="❌ | <b>Geben Sie eine Modul-ID, URL oder antworten Sie auf eine .py-Datei!</b>",
        repo_added="✅ | <b>Repository hinzugefügt: <code>{url}</code></b>",
        repo_removed="✅ | <b>Repository entfernt.</b>",
        invalid_file="❌ | <b>NUR .PY- UND .ZIP-DATEIEN WERDEN AKZEPTIERT!</b>",
    ),
    jp=Strings(
        downloading="⏳ | <b>ダウンロード中...</b>",
        fetching="⏳ | <b><code>{id}</code> を処理中...</b>",
        repo_not_found="❌ | <b>モジュール <code>{id}</code> がどのリポジトリにも見つかりません。</b>",
        search_empty="❌ | <b>クエリ <code>{query}</code> に一致するモジュールはありません。</b>",
        done="✅ | <b>モジュール <code>{name}</code> を正常に読み込みました!</b>",
        error="❌ | <b>エラー: <code>{err}</code></b>",
        reloading="⏳ | <b>すべてのモジュールを再読み込み中...</b>",
        reloaded="♻️ | <b>モジュールを再読み込みしました。合計: {count}</b>",
        unloaded="✅ | <b>モジュール <code>{name}</code> をアンロードしました。</b>",
        search_header="<b>{icon} | <a href='{url}'>{type} Repository</a></b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>",
        search_item="📦 | <b><a href='{raw_url}'>{name}</a></b> [v{version}]<br>┗ <code>.mdl {cmd_id}</code><br><br>",
        confirm_unsafe="⚠️ | <b>セキュリティ警告</b><br><b>{source}</b> からモジュールをインストールしようとしています — <b>未検証</b>のソースです。<br>このモジュールはレビューされておらず、悪意のあるコードを含む可能性があります。<br><br><b>このモジュールをインストールしてもよろしいですか？</b>",
        confirm_unsafe_url="⚠️ | <b>非システムモジュール</b><br>システムリポジトリ<b>以外</b>からモジュールをインストールしようとしています。<br><br>🔗 <b>URL:</b> <code>{url}</code><br><br>インストール前にコードを確認してください。<br><br><b>このモジュールをインストールしますか？</b>",
        security_summary="<b>🔒 | コミュニティモジュールのセキュリティ</b><br><br>"
            "あなたは<b>非システム</b>ソースからモジュールをインストールしようとしています。"
            "注意:<br><br>"
            "⬥ サードパーティモジュールのインストールは<b>自己責任</b>です。<br>"
            "⬥ コアはモジュールをサンドボックスで<b>実行しません</b>。<br>"
            "⬥ コード内の不明なリンク、難読化、隠しコマンドを確認してください。<br>"
            "⬥ システムリポジトリは信頼されています — すべてのモジュールはレビュー済みです。<br><br>"
            "<b>続行してもよろしいですか？</b>",
        security_declined="❌ | <b>インストールがキャンセルされました。</b> <b>システムリポジトリ</b>の使用をお勧めします — すべてのモジュールはレビュー済みです。<br><br>検索: <code>.msearch &lt;クエリ&gt;</code>",
        repo_confirm="⚠️ | <b>信頼できないソース</b><br>リポジトリ <code>{url}</code> を追加しようとしています — これは<b>システム</b>リポジトリではありません。<br><br>このソースのモジュールはレビューされておらず、危険な可能性があります。<br><br><b>このリポジトリを追加してもよろしいですか？</b>",
        confirm_cancelled="❌ | <b>ユーザーによりインストールがキャンセルされました。</b>",
        dev_usage="❌ | <b>直接リンク/ファイルには <code>dev</code> プレフィックスが必要です。</b>",
        no_args="❌ | <b>モジュールID、URLを指定するか、.pyファイルに返信してください!</b>",
        repo_added="✅ | <b>リポジトリを追加しました: <code>{url}</code></b>",
        repo_removed="✅ | <b>リポジトリを削除しました。</b>",
        invalid_file="❌ | <b>.PY および .ZIP ファイルのみ受け付けます!</b>",
    ),
)


class MdlPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    target: str = ""
    is_dev: bool = False

    @model_validator(mode='before')
    @classmethod
    def parse_mdl(cls, v: Any):
        if not v or not isinstance(v, str):
            return {"target": ""}
        parts = v.split(maxsplit=1)
        if parts[0].lower() == "dev":
            return {"is_dev": True, "target": parts[1] if len(parts) > 1 else ""}
        return {"is_dev": False, "target": v}

class RepoPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    url: str

    @model_validator(mode='before')
    @classmethod
    def parse(cls, v: Any):
        if isinstance(v, str):
            return {"url": cutils.convert_repo_url(v.strip())}
        return {"url": ""}

class SearchPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(default="")

    @model_validator(mode='before')
    @classmethod
    def parse_search(cls, v: Any):
        return {"query": v.strip()} if isinstance(v, str) else {"query": ""}

class UnmdPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str

    @model_validator(mode='before')
    @classmethod
    def parse(cls, v: Any):
        return {"name": v.strip()} if isinstance(v, str) else {"name": ""}

class UpdatePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = ""

    @model_validator(mode='before')
    @classmethod
    def parse(cls, v: Any):
        return {"name": v.strip()} if isinstance(v, str) else {"name": ""}


@loader.tds
class LoaderModule(loader.Module):
    config = {
        "repo_url": loader.ConfigValue("https://raw.githubusercontent.com/MxUserBot/mx-modules/main", "Main system repository URL", required=True),
        "first_unsafe_warn_ok": loader.ConfigValue(False, "User read and accepted the community module security warning"),
        "dev_warn_ok": loader.ConfigValue(False, "User accepted dev/file installation warning")
    }

    strings = locales

    async def _matrix_start(self, mx):
        self.repo = loader.RepoManager(mx, self._db, self.config.get("repo_url"))
        self._unsafe_warn_ok = await self._get("LoaderModule", "unsafe_warn_ok", False)

    async def _security_gate(self, mx, event, payload: MdlPayload, source_verified: bool, source_url: str = "", is_file: bool = False, on_confirm=None):
        is_direct = payload.target.startswith(("http", "import ", "from ")) or is_file

        if not is_direct and source_verified:
            return True

        if not self._unsafe_warn_ok:
            ok = await self._show_first_warning(mx, event)
            if not ok:
                return False
            self._unsafe_warn_ok = True
            await self._set("LoaderModule", "unsafe_warn_ok", True)

        await self._confirm_unsafe_install(mx, event, source_url or payload.target, on_confirm=on_confirm)
        return False

    async def _show_first_warning(self, mx, event):
        confirmed = asyncio.Event()
        result = [False]

        async def _callback(ctx):
            if ctx.payload == "yes":
                result[0] = True
            else:
                await ctx.edit(self.strings["security_declined"])
            confirmed.set()
            await ctx.close()

        markup = EmojiKeyBoard(
            rows=[[
                EmojiButton("✅", "yes"),
                EmojiButton("❌", "no"),
            ]],
            callback=_callback,
        )

        await utils.answer(
            mx,
            self.strings["security_summary"],
            event=event,
            reply_markup=markup,
        )
        try:
            await asyncio.wait_for(confirmed.wait(), timeout=120)
        except asyncio.TimeoutError:
            return False
        return result[0]

    async def _confirm_unsafe_install(self, mx, event, url: str, on_confirm=None):
        async def _callback(ctx):
            if ctx.payload == "yes":
                if on_confirm:
                    await on_confirm(ctx)
            else:
                await ctx.edit(self.strings["confirm_cancelled"])
            await ctx.close()

        markup = EmojiKeyBoard(
            rows=[[
                EmojiButton("✅", "yes"),
                EmojiButton("❌", "no"),
            ]],
            callback=_callback,
        )

        await utils.answer(
            mx,
            self.strings["confirm_unsafe_url"].format(url=url),
            event=event,
            reply_markup=markup,
        )
        return False

    @loader.command(aliases=["ms"], security=loader.OWNER)
    async def msearch(self, mx, event: MessageEvent, payload: SearchPayload):
        """<query> — search module in repo"""
        if not payload.query:
            raise UsageError
            
        results = await self.repo.search(payload.query)
        if not results:
            return await utils.answer(mx, self.strings["search_empty"].format(query=payload.query))

        results.sort(key=lambda x: not x["is_verified"])

        flat_list = []
        for res in results:
            prefix = ""
            if not res["is_verified"]:
                # Красивый префикс из ника GitHub или "comm/"
                parts = res["repo_url"].split("/")
                if "github" in res["repo_url"] and len(parts) > 3:
                    prefix = f"{parts[3]}/"
                else:
                    prefix = "comm/"

            for mod in res["modules"]:
                flat_list.append({
                    "repo_info": res,
                    "mod_info": mod,
                    "prefix": prefix
                })

        def render_page(items_slice, page_num, total_pages):
            content = []
            last_repo_url = None
            
            for item in items_slice:
                res = item["repo_info"]
                mod = item["mod_info"]
                prefix = item["prefix"]
                
                if res["repo_url"] != last_repo_url:
                    if res["is_verified"]:
                        header = self.strings["search_header"].format(
                            icon="✅", 
                            type="SYSTEM", 
                            url=res["repo_url"]
                        )
                    else:
                        header = "<b>👥 | COMMUNITY Repository</b><br>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯<br>"
                    
                    content.append(header)
                    last_repo_url = res["repo_url"]
                
                mod_name = mod.get("name") or mod.get("id", "Unknown")
                content.append(
                    self.strings["search_item"].format(
                        name=mod_name,
                        raw_url=mod.get("url", "#"),
                        version=mod.get("version", "1.0.0"),
                        cmd_id=f"{prefix}{mod.get('id')}"
                    )
                )
            
            footer = f"<br><i>Page {page_num + 1} of {total_pages}</i>"
            return "".join(content) + footer

        per_page = 5
        pages = []
        total_mod_count = len(flat_list)
        total_pages_count = (total_mod_count - 1) // per_page + 1
        
        for i in range(0, total_mod_count, per_page):
            pages.append(render_page(flat_list[i : i + per_page], len(pages), total_pages_count))

        if len(pages) == 1:
            await utils.answer(mx, pages[0])
            return

        async def on_page(ctx):
            page = ctx.data.get("page", 0)
            if ctx.payload == "prev":
                page = page - 1 if page > 0 else len(pages) - 1
            else:
                page = (page + 1) % len(pages)
            
            ctx.data["page"] = page
            await ctx.edit(pages[page])

        markup = EmojiKeyBoard(
            rows=[[
                EmojiButton(emoji="⬅️", data="prev"),
                EmojiButton(emoji="➡️", data="next"),
            ]],
            callback=on_page,
            data={"page": 0},
            remove_clicked=True,
        )

        await utils.answer(mx, pages[0], event=event, reply_markup=markup)


    @loader.command(security=loader.OWNER)
    async def mdl(self, mx, event: MessageEvent, payload: MdlPayload):
        """[dev] <id/url/reply> — install module."""
        reply_event = await utils.get_reply_event(mx, event)

        if reply_event:
            fname, content = await self.repo.get_file_content(reply_event)

            if not fname.endswith((".py", ".zip")):
                raise UsageError(self.strings["invalid_file"])

            install_kw = {"filename": fname}
            if fname.endswith(".zip"):
                install_kw["code"] = content
            else:
                install_kw["code"] = content.decode("utf-8", errors="ignore")

            status_id = await utils.answer(mx, self.strings["downloading"])

            async def _install(ctx):
                await ctx.close()
                if await self.repo.install(**install_kw, event=event):
                    await utils.answer(mx, self.strings["done"].format(name=fname), edit_id=status_id)
                    await self.loader.show_module_help(mx, event, fname)
                else:
                    await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)

            if not await self._security_gate(mx, event, payload, False, source_url=payload.target, is_file=True, on_confirm=_install):
                return

            if await self.repo.install(**install_kw, event=event):
                await utils.answer(mx, self.strings["done"].format(name=fname), edit_id=status_id)
                await self.loader.show_module_help(mx, event, fname)
            else:
                await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)
            return

        if not payload.target:
            raise UsageError(self.strings["no_args"])

        status_id = await utils.answer(mx, self.strings["fetching"].format(id=payload.target[:20]))
        url, source = await self.repo.resolve_and_download(payload.target)

        if not url:
            return await utils.answer(mx, self.strings["repo_not_found"].format(id=payload.target), edit_id=status_id)

        async def _install(ctx):
            await ctx.close()
            await utils.answer(mx, self.strings["downloading"], edit_id=status_id)
            if await self.repo.install(target=payload.target, event=event):
                    filename = url.split("/")[-1]
                    if not filename.endswith((".py", ".zip")): filename += ".py"
                    await utils.answer(mx, self.strings["done"].format(name=filename), edit_id=status_id)
                    await self.loader.show_module_help(mx, event, filename)
            else:
                    await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)

        if not await self._security_gate(mx, event, payload, getattr(source, "is_verified", False), source_url=url, on_confirm=_install):
            return

        await utils.answer(mx, self.strings["downloading"], edit_id=status_id)
        if await self.repo.install(target=payload.target, event=event):
            filename = url.split("/")[-1]
            if not filename.endswith((".py", ".zip")): filename += ".py"
            await utils.answer(mx, self.strings["done"].format(name=filename), edit_id=status_id)
            await self.loader.show_module_help(mx, event, filename)
        else:
            await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)


    @loader.command(security=loader.OWNER)
    async def addrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — add repo"""
        if not payload.url:
            raise UsageError(self.strings["no_args"])

        test = await self.repo._fetch_index(payload.url)
        if not test: 
            return await utils.answer(mx, "❌ | <b>Invalid repo or index!</b>")

        confirmed = asyncio.Event()
        result = [False]

        async def _callback(ctx):
            if ctx.payload == "yes":
                repos = await self.repo.get_repos()
                if payload.url not in repos:
                    repos.append(payload.url)
                    await self._set("LoaderModule", "community_repos", repos)
                result[0] = True
                await ctx.edit(self.strings["repo_added"].format(url=payload.url))
            else:
                await ctx.edit(self.strings["confirm_cancelled"])
            await ctx.close()
            confirmed.set()

        markup = EmojiKeyBoard(
            rows=[[
                EmojiButton("✅", "yes"),
                EmojiButton("❌", "no"),
            ]],
            callback=_callback,
        )

        await utils.answer(
            mx,
            self.strings["repo_confirm"].format(url=payload.url),
            event=event,
            reply_markup=markup,
        )
        try:
            await asyncio.wait_for(confirmed.wait(), timeout=120)
        except asyncio.TimeoutError:
            pass


    @loader.command(security=loader.OWNER)
    async def delrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — delete repo"""
        if not payload.url:
            raise UsageError(self.strings["no_args"])
            
        repos = await self.repo.get_repos()
        if payload.url in repos:
            repos.remove(payload.url)
            await self._set("LoaderModule", "community_repos", repos)
            await utils.answer(mx, self.strings["repo_removed"])


    @loader.command(security=loader.OWNER)
    async def reload(self, mx, event: MessageEvent):
        """Reload everything modules!"""
        status_id = await utils.answer(mx, self.strings["reloading"])
        errors = await self.loader.register_all(mx)
        msg = self.strings["reloaded"].format(count=len(mx.active_modules))
        if errors:
            error_lines = [f"  ⚠️ <b>{e['name']}</b>: <code>{cutils.escape_html(e['error'])}</code>" for e in errors]
            msg += "<br><br><b>Failed modules:</b><br>" + "<br>".join(error_lines)
        await utils.answer(mx, msg, edit_id=status_id)


    @loader.command(security=loader.OWNER)
    async def unmd(self, mx, event: MessageEvent, payload: UnmdPayload):
        """<name> — delete module"""
        if not payload.name:
            raise UsageError(self.strings["no_args"])
            
        actual_name = await self.repo.uninstall(payload.name)
        await utils.answer(mx, self.strings["unloaded"].format(name=actual_name))


    @loader.command(security=loader.OWNER)
    async def update(self, mx, event: MessageEvent, payload: UpdatePayload):
        """[all|<name>] — update modules"""
        if not payload.name:
            raise UsageError(self.strings["no_args"])

        if payload.name.lower() == "all":
            status_id = await utils.answer(mx, "⏳ | <b>Checking for updates...</b>")
            updates = await self.repo.check_updates()
            if not updates:
                await utils.answer(mx, "✅ | <b>All modules are up to date.</b>", edit_id=status_id)
                return
            success = []
            failed = []
            for upd in updates:
                try:
                    await self.repo.install(target=upd["module_id"], event=event)
                    success.append(upd["name"])
                except Exception as e:
                    failed.append(f"{upd['name']}: {e}")
            msg = f"♻️ | <b>Updated {len(success)} module(s).</b>"
            if failed:
                msg += "<br><br><b>Failed:</b><br>" + "<br>".join(f"  ⚠️ <code>{cutils.escape_html(str(f))}</code>" for f in failed)
            await utils.answer(mx, msg, edit_id=status_id)
            return

        url, source = await self.repo.resolve_and_download(payload.name)
        if not url:
            await utils.answer(mx, self.strings["repo_not_found"].format(id=payload.name))
            return
        status_id = await utils.answer(mx, self.strings["fetching"].format(id=payload.name))
        try:
            if await self.repo.install(target=payload.name, event=event):
                filename = url.split("/")[-1]
                if not filename.endswith((".py", ".zip")):
                    filename += ".py"
                await utils.answer(mx, self.strings["done"].format(name=payload.name), edit_id=status_id)
                await self.loader.show_module_help(mx, event, filename)
            else:
                await utils.answer(mx, self.strings["error"].format(err="Update failed!"), edit_id=status_id)
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)), edit_id=status_id)