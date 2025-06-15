/**
 * アプリケーション全体で一貫したログ出力を提供するロガーモジュール。
 *
 * このロガーは、ログレベルに応じてコンソールに色付きのメッセージを出力します。
 * 開発中は詳細なデバッグ情報を提供し、本番環境ではエラーのみを記録するなど、
 * 環境に応じた設定変更も可能です。
 *
 * @example
 * import logger from '@/lib/logger';
 * logger.info('これは情報メッセージです');
 * logger.warn('これは警告メッセージです');
 * logger.error('これはエラーメッセージです');
 */

const LOG_PREFIX = '[EP-X]';

type LogLevel = 'info' | 'warn' | 'error' | 'debug';

const COLORS: Record<LogLevel, string> = {
  info: '#3b82f6',  // blue-500
  warn: '#f59e0b',  // amber-500
  error: '#ef4444', // red-500
  debug: '#a855f7', // purple-500
};

/**
 * ログレベルに応じたスタイルでコンソールにメッセージを出力します。
 * @param level ログレベル ('info', 'warn', 'error', 'debug')
 * @param message 出力するメッセージ
 * @param optionalParams その他の出力パラメータ
 */
function log(level: LogLevel, message: any, ...optionalParams: any[]) {
  const color = COLORS[level];
  const timestamp = new Date().toISOString();

  console[level](
    `%c${LOG_PREFIX} [${level.toUpperCase()}]`,
    `color: ${color}; font-weight: bold;`,
    message,
    ...optionalParams,
    `(@ ${timestamp})`
  );
}

const logger = {
  info: (message: any, ...optionalParams: any[]) => log('info', message, ...optionalParams),
  warn: (message: any, ...optionalParams: any[]) => log('warn', message, ...optionalParams),
  error: (message: any, ...optionalParams: any[]) => log('error', message, ...optionalParams),
  debug: (message: any, ...optionalParams: any[]) => {
    // 開発モードでのみデバッグログを出力するなどの制御も可能
    if (import.meta.env.DEV) {
      log('debug', message, ...optionalParams);
    }
  },
};

export default logger; 