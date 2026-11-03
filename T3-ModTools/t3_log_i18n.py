"""Shared console messages and lossless technical diagnostic files.

Tool-owned messages are translated explicitly. External generator output and Python
tracebacks are saved verbatim, rather than being guessed at or shown as untranslated
console prose. IDs, paths, hashes and exception class names remain technical data.
"""
from __future__ import annotations

import tempfile
from pathlib import Path


LOG_I18N: dict[str, dict[str, str]] = {
    "en": {
        "dependency_disabled": "Disabled {project}: required mods are disabled or missing: {dependencies}.",
        "dependency_enabled": "Enabled {project}, required by {dependent}.",
        "cache_assets": "Incremental build: {compressed} files compressed; {reused} reused from cache.",
        "cache_generator": "Unchanged generator and dependencies; reusing: {project}",
        "cache_build": "No changes detected; the existing package and modded binaries are up to date.",
        "cache_record_failed": "Build completed, but the cache record could not be saved.",
        "generated_assets_rebuild": "Generated assets are enabled; rebuilding Mods.Cod and the modded executable together...",
        "anm_compatibility": "ANM compatibility: {count} animations corrected automatically; {outside} outside the validated profile. Report: {path}",
        "pack_creating": "Generating a mod pack from {count} enabled mods...",
        "compiled_cleaning": "Cleaning previous compiled mod artifacts...",
        "backup_cleanup_failed": "Warning: could not remove the old build backup {path} ({error_type}).",
        "generator_sync": "Synchronizing runtime patch generator: {project}/{script}",
        "generator_done": "Runtime patch generator completed: {project}",
        "generator_details": "Generator diagnostic details for {project}: {path}",
        "migration_moved": "Moved tool data: {source} → {destination}",
        "migration_conflict": "Existing tool data requires attention: {source} → {destination}",
        "migration_failed": "Tool data migration failed ({error_type}).",
        "migration_complete": "Tool data is now stored in: {path}",
        "loader_rebuild_required": "Enable the mods you want to use, then choose Build Mods + Modded EXE to rebuild the package and binaries together in the new location.",
        "data_folder": "Tool data folder: {path}",
        "operation_failed": "Operation failed ({error_type}). Diagnostic details: {path}",
        "operation_failed_no_details": "Operation failed ({error_type}); the diagnostic file could not be saved.",
        "asset_skipped": "Model skipped: {source}. Diagnostic details: {path}",
        "original_hash": "Original {name} SHA-256: {sha256}",
        "modded_hash": "Modified {name} SHA-256: {sha256}",
        "patches_applied": "Executable patches applied: {count}",
        "patch_applied": "  [{target}] {mod_id}/{patch_id} @ 0x{offset:X} ({size} bytes)",
        "mod_list_entry": "{prefix} {index:02d}. {name} ({id}) - {files} files",
    },
    "es": {
        "dependency_disabled": "Se desactivó {project}: faltan o están desactivados los mods requeridos: {dependencies}.",
        "dependency_enabled": "Se activó {project}, requerido por {dependent}.",
        "cache_assets": "Compilación incremental: {compressed} archivos comprimidos; {reused} reutilizados de la caché.",
        "cache_generator": "Generador y dependencias sin cambios; reutilizando: {project}",
        "cache_build": "No se detectaron cambios; el paquete y los binarios modificados ya están actualizados.",
        "cache_record_failed": "La compilación terminó, pero no se pudo guardar el registro de la caché.",
        "generated_assets_rebuild": "Hay recursos generados habilitados; se recompilarán Mods.Cod y el ejecutable modificado juntos...",
        "anm_compatibility": "Compatibilidad ANM: {count} animaciones corregidas automáticamente; {outside} fuera del perfil validado. Informe: {path}",
        "pack_creating": "Generando un paquete con {count} mods habilitados...",
        "compiled_cleaning": "Limpiando los archivos de la compilación anterior...",
        "backup_cleanup_failed": "Advertencia: no se pudo eliminar el respaldo de la compilación anterior {path} ({error_type}).",
        "generator_sync": "Sincronizando el generador de parches: {project}/{script}",
        "generator_done": "Generador de parches completado: {project}",
        "generator_details": "Detalles de diagnóstico del generador de {project}: {path}",
        "migration_moved": "Datos de la herramienta trasladados: {source} → {destination}",
        "migration_conflict": "Los datos existentes de la herramienta requieren atención: {source} → {destination}",
        "migration_failed": "Falló la migración de los datos de la herramienta ({error_type}).",
        "migration_complete": "Los datos de la herramienta ahora se guardan en: {path}",
        "loader_rebuild_required": "Activá los mods que quieras usar y elegí Compilar Mods + EXE modificado para reconstruir juntos el paquete y los binarios en la nueva ubicación.",
        "data_folder": "Carpeta de datos de la herramienta: {path}",
        "operation_failed": "La operación falló ({error_type}). Detalles de diagnóstico: {path}",
        "operation_failed_no_details": "La operación falló ({error_type}); no se pudo guardar el archivo de diagnóstico.",
        "asset_skipped": "Modelo omitido: {source}. Detalles de diagnóstico: {path}",
        "original_hash": "SHA-256 del {name} original: {sha256}",
        "modded_hash": "SHA-256 del {name} modificado: {sha256}",
        "patches_applied": "Parches ejecutables aplicados: {count}",
        "patch_applied": "  [{target}] {mod_id}/{patch_id} @ 0x{offset:X} ({size} bytes)",
        "mod_list_entry": "{prefix} {index:02d}. {name} ({id}) - {files} archivos",
    },
    "ru": {
        "dependency_disabled": "Отключён {project}: необходимые моды отключены или отсутствуют: {dependencies}.",
        "dependency_enabled": "Включён {project}, необходимый для {dependent}.",
        "cache_assets": "Инкрементальная сборка: сжато файлов — {compressed}; использовано из кэша — {reused}.",
        "cache_generator": "Генератор и зависимости не изменились; повторное использование: {project}",
        "cache_build": "Изменений нет; пакет и изменённые бинарные файлы уже актуальны.",
        "cache_record_failed": "Сборка завершена, но запись кэша сохранить не удалось.",
        "generated_assets_rebuild": "Включены генерируемые ресурсы; Mods.Cod и изменённый исполняемый файл будут пересобраны вместе...",
        "anm_compatibility": "Совместимость ANM: автоматическая коррекция для {count} анимаций; вне проверенного профиля: {outside}. Отчёт: {path}",
        "pack_creating": "Формирование сборки из {count} включённых модов...",
        "compiled_cleaning": "Удаление файлов предыдущей сборки...",
        "backup_cleanup_failed": "Предупреждение: не удалось удалить резервную копию предыдущей сборки {path} ({error_type}).",
        "generator_sync": "Синхронизация генератора патчей: {project}/{script}",
        "generator_done": "Генератор патчей завершён: {project}",
        "generator_details": "Диагностика генератора {project}: {path}",
        "migration_moved": "Данные программы перемещены: {source} → {destination}",
        "migration_conflict": "Существующие данные программы требуют внимания: {source} → {destination}",
        "migration_failed": "Не удалось перенести данные программы ({error_type}).",
        "migration_complete": "Данные программы теперь хранятся в: {path}",
        "loader_rebuild_required": "Включите нужные моды и выберите «Собрать моды + изменённый EXE», чтобы пересобрать пакет и бинарные файлы вместе в новой папке.",
        "data_folder": "Папка данных программы: {path}",
        "operation_failed": "Операция завершилась ошибкой ({error_type}). Диагностика: {path}",
        "operation_failed_no_details": "Операция завершилась ошибкой ({error_type}); не удалось сохранить файл диагностики.",
        "asset_skipped": "Модель пропущена: {source}. Диагностика: {path}",
        "original_hash": "SHA-256 исходного {name}: {sha256}",
        "modded_hash": "SHA-256 изменённого {name}: {sha256}",
        "patches_applied": "Применено патчей исполняемых файлов: {count}",
        "patch_applied": "  [{target}] {mod_id}/{patch_id} @ 0x{offset:X} ({size} байт)",
        "mod_list_entry": "{prefix} {index:02d}. {name} ({id}) - файлов: {files}",
    },
    "pt": {
        "dependency_disabled": "{project} foi desativado: mods necessários desativados ou ausentes: {dependencies}.",
        "dependency_enabled": "{project} foi ativado, necessário para {dependent}.",
        "cache_assets": "Compilação incremental: {compressed} arquivos comprimidos; {reused} reutilizados do cache.",
        "cache_generator": "Gerador e dependências sem alterações; reutilizando: {project}",
        "cache_build": "Nenhuma alteração detectada; o pacote e os binários modificados já estão atualizados.",
        "cache_record_failed": "A compilação terminou, mas não foi possível salvar o registro do cache.",
        "generated_assets_rebuild": "Há recursos gerados ativados; Mods.Cod e o executável modificado serão recompilados juntos...",
        "anm_compatibility": "Compatibilidade ANM: {count} animações corrigidas automaticamente; {outside} fora do perfil validado. Relatório: {path}",
        "pack_creating": "Gerando um pacote com {count} mods ativados...",
        "compiled_cleaning": "Limpando os arquivos da compilação anterior...",
        "backup_cleanup_failed": "Aviso: não foi possível remover o backup da compilação anterior {path} ({error_type}).",
        "generator_sync": "Sincronizando o gerador de patches: {project}/{script}",
        "generator_done": "Gerador de patches concluído: {project}",
        "generator_details": "Detalhes de diagnóstico do gerador de {project}: {path}",
        "migration_moved": "Dados da ferramenta movidos: {source} → {destination}",
        "migration_conflict": "Os dados existentes da ferramenta precisam de atenção: {source} → {destination}",
        "migration_failed": "Falha na migração dos dados da ferramenta ({error_type}).",
        "migration_complete": "Os dados da ferramenta agora são armazenados em: {path}",
        "loader_rebuild_required": "Ative os mods que deseja usar e escolha Compilar mods + EXE modificado para recompilar o pacote e os binários juntos na nova localização.",
        "data_folder": "Pasta de dados da ferramenta: {path}",
        "operation_failed": "A operação falhou ({error_type}). Detalhes de diagnóstico: {path}",
        "operation_failed_no_details": "A operação falhou ({error_type}); não foi possível salvar o arquivo de diagnóstico.",
        "asset_skipped": "Modelo ignorado: {source}. Detalhes de diagnóstico: {path}",
        "original_hash": "SHA-256 do {name} original: {sha256}",
        "modded_hash": "SHA-256 do {name} modificado: {sha256}",
        "patches_applied": "Patches de executáveis aplicados: {count}",
        "patch_applied": "  [{target}] {mod_id}/{patch_id} @ 0x{offset:X} ({size} bytes)",
        "mod_list_entry": "{prefix} {index:02d}. {name} ({id}) - {files} arquivos",
    },
}


def log_tr(language: str, key: str, **values: object) -> str:
    translations = LOG_I18N.get(language, LOG_I18N["en"])
    return translations[key].format(**values)


def write_diagnostic(directory: Path, details: str) -> Path:
    """Persist raw diagnostics without replacing previous failure/generator details."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stream = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix="diagnostic_", suffix=".log", delete=False,
        )
    except OSError:
        # A failed output directory should not hide the original failure.
        stream = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="t3_modtools_diagnostic_",
            suffix=".log", delete=False,
        )
    with stream:
        stream.write(details)
    return Path(stream.name)


def diagnostic_message(language: str, directory: Path, details: str, error_type: str) -> str:
    """Return a localized notice while preserving the unmodified diagnostic text."""
    try:
        path = write_diagnostic(directory, details)
    except OSError:
        return log_tr(language, "operation_failed_no_details", error_type=error_type)
    return log_tr(language, "operation_failed", error_type=error_type, path=path)
