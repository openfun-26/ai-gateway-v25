# Cloudflare API Token 中文操作指南

## 📍 访问地址
- **英文版**：https://dash.cloudflare.com/profile/api-tokens
- **中文版**：https://dash.cloudflare.com/zh-cn/profile/api-tokens

## 📋 详细步骤（中文版）

### 第一步：登录Cloudflare控制台
1. 打开浏览器，访问：https://dash.cloudflare.com/zh-cn/profile/api-tokens
2. 使用你的GitHub账号登录（如果是首次使用）
3. 选择你的域名账户

### 第二步：创建API Token
1. **点击"创建令牌"按钮**
   - 在页面右上角找到"创建令牌"按钮
   - 点击进入创建页面

2. **选择模板**
   - 在"开始使用模板"部分
   - 选择 **"编辑区域DNS"** 模板
   - 点击"使用模板"

3. **配置令牌权限**
   - **区域资源**：
     - 选择"特定区域"（如果只管理一个域名）
     - 或选择"所有区域"（管理多个域名）
   - **权限**：
     - 确保 **"区域：DNS：编辑"** 权限被勾选
     - 这是必需的权限，用于部署Worker

4. **配置区域（如果选择"特定区域"）**
   - 从下拉菜单选择你的域名
   - **Zone ID获取方法**：
     - 返回Cloudflare主控制台
     - 选择你的域名
     - 页面右下角会显示"区域 ID"（Zone ID）
     - 复制这个ID（格式：xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx）

### 第三步：创建令牌
1. **填写令牌名称**
   - 输入一个描述性名称，如："AI Gateway v25 部署"
   - 这有助于你识别这个令牌的用途

2. **设置过期时间（可选）**
   - 可以设置令牌的过期时间
   - 建议设置较长的有效期，比如1年

3. **点击"继续"**
   - 确认配置无误后点击"继续"按钮

4. **点击"创建令牌"**
   - 再次确认所有配置
   - 点击"创建令牌"按钮

### 第四步：保存令牌
1. **复制令牌**
   - 创建成功后，会显示一个长字符串的令牌
   - **立即复制这个令牌**，因为页面刷新后就看不到了
   - 令牌格式：`xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

2. **安全存储**
   - 将令牌保存在安全的地方（如密码管理器）
   - 不要将令牌分享给他人

## ⚠️ 重要提醒

### 令牌格式示例
```
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
- 这是一个32位的字符序列
- 每个字符都是字母或数字
- 没有特殊字符

### 常见问题解决

#### 1. 找不到"创建令牌"按钮
- 确保你登录的是正确的Cloudflare账户
- 检查是否选择了正确的域名账户

#### 2. Zone ID在哪里找？
1. 登录Cloudflare控制台：https://dash.cloudflare.com/zh-cn
2. 选择你的域名
3. 查看页面右下角，显示"区域 ID"
4. 复制这个ID

#### 3. 权限配置错误
- 确保"区域：DNS：编辑"权限被勾选
- 如果权限不足，可能需要升级账户

#### 4. 令牌创建失败
- 检查网络连接
- 确保账户有足够的权限
- 尝试清除浏览器缓存后重试

## 🔄 下一步：设置GitHub Secret

获取到令牌后，按照以下步骤设置：

1. **访问GitHub仓库设置**
   - https://github.com/openfun-26/ai-gateway-v25/settings/secrets/actions

2. **添加新的仓库密钥**
   - 点击"New repository secret"
   - Name: `CLOUDFLARE_API_TOKEN`
   - Value: [粘贴你的令牌]
   - 点击"Add secret"

3. **等待自动部署**
   - 设置完成后，GitHub Actions会自动运行
   - 可以在Actions页面查看部署状态

## 📞 获取帮助

如果遇到问题：
- **GitHub Issues**：https://github.com/openfun-26/ai-gateway-v25/issues
- **Cloudflare文档**：https://developers.cloudflare.com/zh-cn/workers/

---

✅ **完成以上步骤后，你的AI Gateway v25项目将自动部署到Cloudflare Workers！**
