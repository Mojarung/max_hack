/** Что делать при беспилотной опасности: одинаково на экране тревоги и в разделе «Безопасность». */
export const ALERT_INSTRUCTIONS = [
  { icon: 'mdi-window-closed-variant', text: 'Отойдите от окон и стеклянных дверей' },
  { icon: 'mdi-stairs-down', text: 'Спуститесь в укрытие или встаньте в коридоре без окон' },
  { icon: 'mdi-cellphone-off', text: 'Не снимайте и не выкладывайте видео с небом' },
  { icon: 'mdi-bell-ring-outline', text: 'Дождитесь сигнала «Отбой», Кузя сообщит' },
] as const
