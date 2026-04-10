/**
 * 共享收件箱预览控制器
 *
 * 复用邮箱管理与账号管理的收件箱消息列表、详情展开、HTML 安全预览与原始字段展示逻辑，
 * 避免两页各自维护一份几乎相同的渲染代码。
 */
(function attachInboxPreview(global) {
    function normalizeInboxMessageId(messageOrId) {
        if (messageOrId && typeof messageOrId === 'object') {
            return String(messageOrId.id || messageOrId.message_id || messageOrId.uuid || '');
        }
        return String(messageOrId || '');
    }

    function formatInboxRawMessage(rawMessage) {
        try {
            return JSON.stringify(rawMessage ?? {}, null, 2);
        } catch (error) {
            console.warn('[inbox-preview] stringify raw inbox message failed', error);
            return String(rawMessage ?? '（原始字段无法序列化）');
        }
    }

    function buildSafeInboxPreviewSrcdoc(htmlBody) {
        return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; media-src 'none'; style-src 'unsafe-inline'; font-src data:; script-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none';">
<style>
body { margin: 0; padding: 12px; font: 14px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #111827; background: #ffffff; word-break: break-word; }
a { color: #2563eb; text-decoration: underline; pointer-events: none; cursor: default; }
img, table, pre, code { max-width: 100%; }
pre { white-space: pre-wrap; }
</style>
</head>
<body>${String(htmlBody || '')}</body>
</html>`;
    }

    function createInboxPreviewController(options = {}) {
        const modal = options.modal || null;
        const meta = options.meta || null;
        const list = options.list || null;
        const fetchInboxData = options.fetchInboxData;
        const formatMeta = options.formatMeta || (() => '');
        const toggleDetailsHandlerName = String(options.toggleDetailsHandlerName || '');
        const emptyTitle = String(options.emptyTitle || '暂无邮件');
        const emptyDescription = String(options.emptyDescription || '当前收件箱未查到最近邮件');
        const loadingText = String(options.loadingText || '正在加载收件箱...');
        const invalidTargetMessage = String(options.invalidTargetMessage || '目标 ID 无效');

        const state = {
            currentTargetId: null,
            messages: [],
            expandedMessageId: null,
        };

        function renderEmptyState(title, description, icon = '📭') {
            return `
                <div class="empty-state">
                    <div class="empty-state-icon">${icon}</div>
                    <div class="empty-state-title">${title}</div>
                    <div class="empty-state-description">${description}</div>
                </div>
            `;
        }

        function renderLoadingState() {
            return `
                <div class="empty-state">
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text" style="width: 80%;"></div>
                </div>
            `;
        }

        function renderBusinessInvite(inviteInfo) {
            if (!inviteInfo || typeof inviteInfo !== 'object') return '';
            const rows = [];
            if (inviteInfo.inviter) {
                rows.push(`
                    <div class="inbox-invite-row">
                        <span class="inbox-invite-label">邀请人</span>
                        <span>${escapeHtml(String(inviteInfo.inviter))}</span>
                    </div>
                `);
            }
            if (inviteInfo.workspace_name) {
                rows.push(`
                    <div class="inbox-invite-row">
                        <span class="inbox-invite-label">工作空间</span>
                        <span>${escapeHtml(String(inviteInfo.workspace_name))}</span>
                    </div>
                `);
            }
            if (inviteInfo.url) {
                const safeUrl = escapeHtml(String(inviteInfo.url));
                rows.push(`
                    <div class="inbox-invite-row">
                        <span class="inbox-invite-label">邀请链接</span>
                        <a class="inbox-invite-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>
                    </div>
                `);
            }
            if (rows.length === 0) return '';
            return `
                <div class="inbox-invite-card">
                    <div class="inbox-invite-title">ChatGPT Business 邀请</div>
                    ${rows.join('')}
                </div>
            `;
        }

        function renderInboxMessageDetails(message) {
            const normalizedMessageId = normalizeInboxMessageId(message);
            const encodedMessageId = encodeURIComponent(normalizedMessageId);
            const htmlBody = String(message.html_body || '').trim();
            const rawMessageText = formatInboxRawMessage(message.raw_message);
            return `
                <div class="inbox-message-details">
                    <section class="inbox-detail-section">
                        <div class="inbox-detail-title">HTML 预览</div>
                        ${htmlBody ? `
                            <iframe
                                class="inbox-html-preview-frame"
                                title="邮件 HTML 预览"
                                sandbox=""
                                referrerpolicy="no-referrer"
                                loading="lazy"
                                data-message-id="${encodedMessageId}"
                            ></iframe>
                        ` : '<div class="inbox-empty-detail">（无 HTML 预览）</div>'}
                    </section>
                    <section class="inbox-detail-section">
                        <details class="inbox-raw-details">
                            <summary>原始字段</summary>
                            <pre class="inbox-raw-json">${escapeHtml(rawMessageText)}</pre>
                        </details>
                    </section>
                </div>
            `;
        }

        function renderMessages(messages = []) {
            if (!Array.isArray(messages) || messages.length === 0) {
                return renderEmptyState(emptyTitle, emptyDescription);
            }
            return messages.map((message) => {
                const normalizedMessageId = normalizeInboxMessageId(message);
                const encodedMessageId = encodeURIComponent(normalizedMessageId);
                const isExpanded = state.expandedMessageId === normalizedMessageId;
                const toggleCall = toggleDetailsHandlerName
                    ? `${toggleDetailsHandlerName}(decodeURIComponent(this.dataset.messageId))`
                    : '';
                return `
                    <article class="inbox-message-item ${isExpanded ? 'is-expanded' : ''}">
                        <div class="inbox-message-head">
                            <span>${escapeHtml(String(message.from || '-'))}</span>
                            <span>${escapeHtml(String(message.received_at || '-'))}${message.is_seen ? ' · 已读' : ' · 未读'}</span>
                        </div>
                        <div class="inbox-message-subject">${escapeHtml(String(message.subject || '-'))}</div>
                        ${renderBusinessInvite(message.business_invite)}
                        <div class="inbox-message-snippet">${escapeHtml(String(message.snippet || '（无正文预览）'))}</div>
                        <div class="inbox-message-actions">
                            <button
                                type="button"
                                class="btn btn-secondary btn-sm inbox-message-toggle"
                                data-message-id="${encodedMessageId}"
                                ${toggleCall ? `onclick="${toggleCall}"` : ''}
                            >${isExpanded ? '收起详情' : '展开详情'}</button>
                        </div>
                        ${isExpanded ? renderInboxMessageDetails(message) : ''}
                    </article>
                `;
            }).join('');
        }

        function hydrateInboxHtmlPreviews(messages = []) {
            if (!list) return;
            const messageMap = new Map(
                (Array.isArray(messages) ? messages : []).map((message) => [normalizeInboxMessageId(message), message])
            );
            list.querySelectorAll('.inbox-html-preview-frame').forEach((frame) => {
                const messageId = decodeURIComponent(frame.dataset.messageId || '');
                const message = messageMap.get(messageId);
                if (!message?.html_body) return;
                frame.srcdoc = buildSafeInboxPreviewSrcdoc(message.html_body);
            });
        }

        function renderCurrentMessages() {
            if (!list) return;
            list.innerHTML = renderMessages(state.messages);
            hydrateInboxHtmlPreviews(state.messages);
        }

        function close() {
            state.currentTargetId = null;
            state.messages = [];
            state.expandedMessageId = null;
            modal?.classList.remove('active');
        }

        async function open(targetId) {
            const normalizedTargetId = Number(targetId || 0) || null;
            if (!normalizedTargetId) {
                toast.error(invalidTargetMessage);
                return;
            }
            state.currentTargetId = normalizedTargetId;
            state.messages = [];
            state.expandedMessageId = null;
            if (meta) meta.textContent = loadingText;
            if (list) list.innerHTML = renderLoadingState();
            modal?.classList.add('active');
            try {
                const data = await fetchInboxData(normalizedTargetId);
                state.messages = Array.isArray(data?.messages) ? data.messages : [];
                state.expandedMessageId = null;
                if (meta) meta.textContent = String(formatMeta(data) || '');
                renderCurrentMessages();
                return data;
            } catch (error) {
                state.messages = [];
                state.expandedMessageId = null;
                if (meta) meta.textContent = '加载失败';
                if (list) {
                    list.innerHTML = renderEmptyState(
                        '收件箱加载失败',
                        escapeHtml(error.message || '未知错误'),
                        '⚠️',
                    );
                }
                toast.error('读取收件箱失败: ' + error.message);
                throw error;
            }
        }

        async function refresh() {
            if (!state.currentTargetId) return;
            return open(state.currentTargetId);
        }

        function toggleDetails(messageId) {
            const normalizedMessageId = normalizeInboxMessageId(messageId);
            state.expandedMessageId = state.expandedMessageId === normalizedMessageId ? null : normalizedMessageId;
            renderCurrentMessages();
        }

        return {
            open,
            close,
            refresh,
            toggleDetails,
            renderMessages,
            renderCurrentMessages,
            buildSafeInboxPreviewSrcdoc,
            getCurrentTargetId: () => state.currentTargetId,
        };
    }

    global.InboxPreview = {
        createInboxPreviewController,
        buildSafeInboxPreviewSrcdoc,
        normalizeInboxMessageId,
    };
})(window);
