/**
 * ==========================================
 * Notion AI Info Extractor / Notion AI 信息提取脚本
 * ==========================================
 * How to use / 使用方法：
 * 1. Login to https://www.notion.so/ai / 登录 https://www.notion.so/ai
 * 2. Press F12 to open DevTools / 按 F12 打开开发者工具
 * 3. Switch to Console tab / 切换到 Console 标签
 * 4. Paste this script and press Enter / 粘贴本脚本并回车
 * 5. Manually enter your token_v2 (from Application → Cookies) / 手动输入你的 token_v2（从 Application → Cookies 复制）
 * 6. Result will be auto-copied to clipboard / 结果会自动复制到剪贴板
 * ==========================================
 */

(function() {
    console.log('%c[Notion AI Info Extractor]', 'font-size: 16px; font-weight: bold; color: #00a699;');
    console.log('%cExtracting information... / 正在提取信息...', 'color: #666;');

    const info = {
        token_v2: 'YOUR_TOKEN_V2_HERE',  // Needs manual entry / 需要手动填入
        space_id: '',
        user_id: '',
        space_view_id: '',
        user_name: '',
        user_email: ''
    };

    // Method 1: Fetch from Notion API / 方法 1: 从 Notion API 获取
    (async function() {
        try {
            const resp = await fetch('/api/v3/loadUserContent', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({}),
                credentials: 'include'
            });

            if (resp.ok) {
                const data = await resp.json();
                const rm = data.recordMap || {};

                // Extract user_id + username/email / 提取 user_id + 用户名/邮箱
                const userIds = Object.keys(rm.notion_user || {});
                if (userIds.length > 0) {
                    info.user_id = userIds[0];
                    const userVal = rm.notion_user[userIds[0]]?.value;
                    if (userVal) {
                        info.user_name = userVal.given_name || userVal.name || '';
                        info.user_email = userVal.email || '';
                    }
                }

                // Extract space_id / 提取 space_id
                const spaceIds = Object.keys(rm.space || {});
                if (spaceIds.length > 0) {
                    info.space_id = spaceIds[0];
                }

                // Extract space_view_id / 提取 space_view_id
                const svIds = Object.keys(rm.space_view || {});
                if (svIds.length > 0) {
                    info.space_view_id = svIds[0];
                }
            }
        } catch (err) {
            console.warn('%c⚠️ API call failed / API 调用失败', 'color: #ff9800;', err.message);
        }

        // Output result / 输出结果
        outputResult();
    })();

    function outputResult() {
        const envOutput = `NOTION_ACCOUNTS='[{"token_v2":"${info.token_v2}","space_id":"${info.space_id}","user_id":"${info.user_id}","space_view_id":"${info.space_view_id}","user_name":"${info.user_name}","user_email":"${info.user_email}"}]'`;

        console.log('%c✅ Extraction complete! / 提取完成！', 'color: #00c853; font-size: 14px; font-weight: bold;');
        console.log('%c📋 Auto-retrieved info / 已自动获取的信息：', 'color: #00c853;');
        console.table({
            'space_id': info.space_id || '❌ Not found / 未获取到',
            'user_id': info.user_id || '❌ Not found / 未获取到',
            'space_view_id': info.space_view_id || '❌ Not found / 未获取到',
            'user_name': info.user_name || '❌ Not found / 未获取到',
            'user_email': info.user_email || '❌ Not found / 未获取到'
        });
        console.log('%c⚠️ Please manually replace the token_v2 value below / 请手动替换下方的 token_v2 值：', 'color: #ff9800; font-weight: bold;');
        console.log('%c' + envOutput, 'color: #00a699;');
        console.log('%c\n💡 Next steps / 使用步骤：', 'color: #666; font-weight: bold;');
        console.log('%c  1. Copy the NOTION_ACCOUNTS=... content above / 复制上面的 NOTION_ACCOUNTS=... 内容', 'color: #666;');
        console.log('%c  2. Replace YOUR_TOKEN_V2_HERE with your actual token_v2 / 将 YOUR_TOKEN_V2_HERE 替换为你的实际 token_v2', 'color: #666;');
        console.log('%c  3. Paste into .env file / 粘贴到 .env 文件中', 'color: #666;');

        // Copy to clipboard / 复制到剪贴板
        navigator.clipboard.writeText(envOutput)
            .then(() => console.log('%c✅ Copied to clipboard / 已复制到剪贴板', 'color: #00c853; font-weight: bold;'))
            .catch(() => console.warn('%c⚠️ Auto-copy failed, please copy manually / 自动复制失败，请手动复制', 'color: #ff9800;'));

        return info;
    }
})();
