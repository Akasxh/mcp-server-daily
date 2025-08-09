import OAuthProvider from '@cloudflare/workers-oauth-provider'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { McpAgent } from 'agents/mcp'
import { z } from 'zod'
import { GoogleHandler } from './google-handler'

// Context from the auth process, encrypted & stored in the auth token
// and provided to the MyMCP as this.props
type Props = {
  name: string
  email: string
  accessToken: string
}

const PHONE_NUMBER = '+919998881729'

export class MyMCP extends McpAgent<Env, Record<string, never>, Props> {
  server = new McpServer({
    name: 'Google OAuth Proxy Demo',
    version: '0.0.1',
  })

  async init() {
    // Simple add tool
    this.server.tool('validate', 'Validated this mcp server to be used by PuchAI', {}, async () => ({
      content: [{ text: String(PHONE_NUMBER), type: 'text' }],
    }))

    // Gmail send email tool
    this.server.tool(
      'send_gmail',
      {
        to: z.string().email(),
        subject: z.string(),
        body: z.string(),
      },
      async ({ to, subject, body }) => {
        if (!this.props.accessToken) {
          return {
            content: [
              {
                text: 'No Google access token found. Please authenticate with Google first.',
                type: 'text',
              },
            ],
          }
        }

        const gmailSendUrl = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        const message = [`To: ${to}`, `Subject: ${subject}`, 'Content-Type: text/plain; charset="UTF-8"', '', body].join('\r\n')

        const base64Encoded = btoa(unescape(encodeURIComponent(message)))
          .replace(/\+/g, '-')
          .replace(/\//g, '_')
          .replace(/=+$/, '')

        const response = await fetch(gmailSendUrl, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${this.props.accessToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            raw: base64Encoded,
          }),
        })

        if (!response.ok) {
          const errorText = await response.text()
          return {
            content: [
              {
                text: `Failed to send email: ${errorText}`,
                type: 'text',
              },
            ],
          }
        }

        return {
          content: [
            {
              text: `Email sent to ${to} successfully!`,
              type: 'text',
            },
          ],
        }
      },
    )

    // Google Drive search files tool
    this.server.tool('search_files', { query: z.string() }, async ({ query }) => {
      if (!this.props.accessToken) {
        return {
          content: [
            {
              text: 'No Google access token found. Please authenticate with Google first.',
              type: 'text',
            },
          ],
        }
      }

      const url =
        'https://www.googleapis.com/drive/v3/files?fields=files(id,name,mimeType)&q=' + encodeURIComponent(`name contains '${query}'`)

      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${this.props.accessToken}` },
      })

      if (!resp.ok) {
        const errorText = await resp.text()
        return {
          content: [{ text: `Drive search failed: ${errorText}`, type: 'text' }],
        }
      }

      const data = (await resp.json()) as {
        files: { id: string; name: string; mimeType: string }[]
      }

      const results = data.files.map((f) => `${f.name} (${f.mimeType}) - gdrive:///${f.id}`).join('\n')

      return {
        content: [{ text: results || 'No files found.', type: 'text' }],
      }
    })

    // Google Drive read file tool
    this.server.tool('read_file', { file_id: z.string() }, async ({ file_id }) => {
      if (!this.props.accessToken) {
        return {
          content: [
            {
              text: 'No Google access token found. Please authenticate with Google first.',
              type: 'text',
            },
          ],
        }
      }

      const id = file_id.startsWith('gdrive:///') ? file_id.replace('gdrive:///', '') : file_id

      const metaResp = await fetch(`https://www.googleapis.com/drive/v3/files/${id}?fields=name,mimeType`, {
        headers: { Authorization: `Bearer ${this.props.accessToken}` },
      })

      if (!metaResp.ok) {
        const errorText = await metaResp.text()
        return {
          content: [{ text: `Failed to fetch file metadata: ${errorText}`, type: 'text' }],
        }
      }

      const { mimeType } = (await metaResp.json()) as {
        name: string
        mimeType: string
      }

      const fileResp = await fetch(`https://www.googleapis.com/drive/v3/files/${id}?alt=media`, {
        headers: { Authorization: `Bearer ${this.props.accessToken}` },
      })

      if (!fileResp.ok) {
        const errorText = await fileResp.text()
        return {
          content: [{ text: `Failed to download file: ${errorText}`, type: 'text' }],
        }
      }

      const buffer = await fileResp.arrayBuffer()

      if (mimeType.startsWith('text/') || mimeType === 'application/json') {
        const text = new TextDecoder().decode(buffer)
        return { content: [{ type: 'text', text }] }
      }

      const base64 = arrayBufferToBase64(buffer)
      if (mimeType.startsWith('image/')) {
        return {
          content: [{ type: 'image', data: base64, mimeType }],
        }
      }

      // Fallback for other binary formats like PDFs
      return {
        content: [
          {
            type: 'text',
            text: base64,
          },
        ],
      }
    })
  }
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  const len = bytes.byteLength
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export default new OAuthProvider({
  apiHandler: MyMCP.mount('/sse') as any,
  apiRoute: '/sse',
  authorizeEndpoint: '/authorize',
  clientRegistrationEndpoint: '/register',
  defaultHandler: GoogleHandler as any,
  tokenEndpoint: '/token',
})
