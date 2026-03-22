export default function ChatMessage({ role, content }) {
  const isUser = role === 'user'

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        <div className="message-content">{content}</div>
      </div>
    </div>
  )
}
