# Yupoo Downloader SaaS — Guia de Deploy

## Estrutura do projeto

```
yupoo-saas/
├── api/                  → Backend Python (FastAPI)
├── frontend/             → Site Next.js (React)
├── nginx/                → Proxy reverso
├── chrome-extension/     → Extensão Chrome
├── docker-compose.yml    → Sobe tudo junto
└── .env.example          → Template de variáveis
```

---

## Passo 1 — Configurar o Google OAuth

1. Acesse https://console.cloud.google.com
2. Crie um projeto novo
3. **APIs e Serviços → Biblioteca** → ative a **Google Drive API**
4. **Credenciais → Criar credenciais → ID do cliente OAuth 2.0**
5. Tipo: **Aplicativo da Web**
6. Origens JS autorizadas: `https://seudominio.com`
7. URIs de redirecionamento: `https://seudominio.com/api/auth/callback`
8. Copie o **Client ID** e **Client Secret**

---

## Passo 2 — Configurar o Stripe

1. Crie conta em https://stripe.com
2. **Dashboard → Produtos** → crie 4 produtos:
   - Starter — R$ 19
   - Pro — R$ 59
   - Business — R$ 149
   - Unlimited — R$ 349
3. Copie o `price_xxx` de cada produto
4. **Developers → API Keys** → copie a **Secret Key** (`sk_live_...`)
5. **Developers → Webhooks → Adicionar endpoint**:
   - URL: `https://seudominio.com/api/credits/webhook`
   - Evento: `checkout.session.completed`
   - Copie o **Webhook Secret** (`whsec_...`)

---

## Passo 3 — Criar o arquivo .env no servidor

No servidor (via SSH ou terminal do Coolify), na pasta do projeto:

```bash
cp .env.example .env
nano .env   # preencha todos os valores
```

Gere o JWT_SECRET:
```bash
openssl rand -hex 32
```

---

## Passo 4 — Deploy no Coolify

### Opção A — Via Git (recomendado)

1. Suba o projeto para um repositório Git (GitHub/GitLab)
2. No Coolify: **New Resource → Docker Compose**
3. Aponte para o repositório
4. Em **Environment Variables**, cole o conteúdo do seu `.env`
5. Clique em **Deploy**

### Opção B — Upload direto

1. Faça upload da pasta no servidor via SCP ou SFTP:
   ```bash
   scp -r yupoo-saas/ usuario@seuservidor.com:~/
   ```
2. No servidor:
   ```bash
   cd yupoo-saas
   cp .env.example .env
   # edite o .env com seus valores
   docker compose up -d --build
   ```

---

## Passo 5 — Apontar o domínio

No Coolify, adicione seu domínio no serviço **nginx** e ative o **HTTPS automático** (Let's Encrypt). O Coolify faz isso com um clique.

Ou configure manualmente no seu DNS:
```
A   @    → IP do servidor
A   www  → IP do servidor
```

---

## Passo 6 — Publicar a extensão Chrome

1. Acesse https://chrome.google.com/webstore/devconsole
2. Pague a taxa única de U$ 5
3. **Edite o arquivo** `chrome-extension/popup.js`:
   - Linha 1: troque `seudominio.com` pelo seu domínio real
4. Zippe a pasta `chrome-extension/`:
   ```bash
   zip -r yupoo-extension.zip chrome-extension/
   ```
5. Faça upload do zip na Chrome Web Store
6. Preencha nome, descrição, screenshots e publique

---

## Comandos úteis no servidor

```bash
# Ver logs da API
docker logs yupoo-api -f

# Ver logs do frontend
docker logs yupoo-frontend -f

# Reiniciar tudo
docker compose restart

# Atualizar após mudanças no código
docker compose up -d --build

# Backup do banco de dados
docker cp yupoo-api:/data/yupoo.db ./backup-$(date +%Y%m%d).db
```

---

## Checklist antes de abrir para o público

- [ ] `.env` preenchido com todos os valores reais
- [ ] HTTPS ativo no domínio
- [ ] Google OAuth com URI de callback correto
- [ ] Stripe em modo live (não test)
- [ ] Webhook do Stripe apontando para o domínio correto
- [ ] `chrome-extension/popup.js` com o domínio real
- [ ] Testou login → compra → download completo

---

## Custos mensais estimados

| Item | Custo |
|---|---|
| Servidor (Coolify — já seu) | R$ 0 |
| Banco SQLite | R$ 0 |
| Google Drive API | R$ 0 |
| Stripe (por transação) | ~3,9% + R$ 0,39 |
| Domínio .com.br | R$ 3,33/mês |
| Chrome Web Store | R$ 27 (uma vez) |
| **Total fixo/mês** | **~R$ 4** |
