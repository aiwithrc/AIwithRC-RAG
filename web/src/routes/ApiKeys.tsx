import { Topbar } from '../components/AppShell';
import { EmptyNote, Page, PageHeader, Section } from '../components/ui';

export default function ApiKeys() {
  return (
    <>
      <Topbar title="API keys" />
      <Page>
        <PageHeader
          title="API keys"
          sub="Connect a model provider. Any OpenAI-compatible endpoint works, including Ollama, OpenAI, Anthropic, OpenRouter and vLLM."
        />
        <Section title="Connected providers">
          <EmptyNote>No providers yet. Adding a connection arrives with the answering pipeline.</EmptyNote>
        </Section>
      </Page>
    </>
  );
}
