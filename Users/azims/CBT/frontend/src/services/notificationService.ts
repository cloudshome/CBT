const NOTIFICATION_STORAGE_KEY = 'ctb_push_notifications_enabled';

export const notificationService = {
  /**
   * Checks if browser supports Web Notifications
   */
  isSupported(): boolean {
    return typeof window !== 'undefined' && 'Notification' in window;
  },

  /**
   * Retrieves current browser notification permission
   */
  getPermission(): NotificationPermission {
    if (!this.isSupported()) return 'denied';
    return Notification.permission;
  },

  /**
   * Checks if user has enabled notifications in app settings and browser granted
   */
  isEnabled(): boolean {
    if (!this.isSupported()) return false;
    const preference = localStorage.getItem(NOTIFICATION_STORAGE_KEY);
    return Notification.permission === 'granted' && preference !== 'false';
  },

  /**
   * Updates user notification preference in localStorage
   */
  setEnabled(enabled: boolean): void {
    localStorage.setItem(NOTIFICATION_STORAGE_KEY, String(enabled));
  },

  /**
   * Requests notification permissions from user
   */
  async requestPermission(): Promise<boolean> {
    if (!this.isSupported()) return false;

    try {
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        this.setEnabled(true);
        // Send a welcome confirmation
        await this.sendNotification('🔔 CTB Web Push Notifications Active', {
          body: 'You will receive instant alerts for Risk Gate rejections and Gemini market briefs.',
          tag: 'welcome-notification',
        });
        return true;
      }
      this.setEnabled(false);
      return false;
    } catch (err) {
      console.error('[NotificationService] Permission request failed:', err);
      return false;
    }
  },

  /**
   * Sends a local notification using ServiceWorkerRegistration or window.Notification
   */
  async sendNotification(
    title: string,
    options?: {
      body?: string;
      icon?: string;
      tag?: string;
      data?: unknown;
    }
  ): Promise<void> {
    if (!this.isEnabled()) return;

    const notificationOptions: NotificationOptions & { renotify?: boolean } = {
      body: options?.body || '',
      icon: options?.icon || '/icon.svg',
      badge: '/icon.svg',
      tag: options?.tag || 'ctb-alert',
      renotify: true,
      data: options?.data,
    };

    try {
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        if (registration && 'showNotification' in registration) {
          await registration.showNotification(title, notificationOptions);
          return;
        }
      }

      // Fallback to standard window Notification
      new Notification(title, notificationOptions);
    } catch (err) {
      console.error('[NotificationService] Error dispatching notification:', err);
    }
  },

  /**
   * Fires a Risk Gate Rejection alert
   */
  async notifyRiskGateAlert(reason: string, details?: string): Promise<void> {
    await this.sendNotification('⚠️ CTB Risk Gate Alert', {
      body: details ? `${reason}\n${details}` : reason,
      tag: 'risk-gate-alert',
    });
  },

  /**
   * Fires an AI Desk Market Brief notification
   */
  async notifyMarketBriefAlert(symbol: string, bias: string, summary: string): Promise<void> {
    const cleanSummary = summary.length > 120 ? `${summary.slice(0, 117)}...` : summary;
    await this.sendNotification(`🧠 CTB AI Brief: ${symbol} [${bias}]`, {
      body: cleanSummary,
      tag: `ai-brief-${symbol}`,
    });
  },
};
