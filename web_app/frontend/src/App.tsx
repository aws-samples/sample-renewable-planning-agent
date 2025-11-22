import { I18nProvider } from "@cloudscape-design/components/i18n";
import messages from "@cloudscape-design/components/i18n/messages/all.en";
import "@cloudscape-design/global-styles/index.css";
import "./index.css";
import { FlashbarProvider } from "./common/contexts/Flashbar";
import Chat from "./pages/Chat";

const LOCALE = "en";

export default function App() {
    return (
        <I18nProvider locale={LOCALE} messages={[messages]}>
            <FlashbarProvider>
                <div style={{ height: "100vh", width: "100vw", overflow: "hidden" }}>
                    <Chat />
                </div>
            </FlashbarProvider>
        </I18nProvider>
    );
}
