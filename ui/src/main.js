import Vue from 'vue';
import App from './App.vue';
import './styles/app.css';
import './styles/face-match.css';
import { createI18n } from './i18n';

const i18nState = Vue.observable({
    locale: 'enu',
    messages: {},
    version: 0,
});

function translateWithState(key, fallback = '', params = null) {
    // Touch a reactive field so Vue re-renders after locale/messages are updated.
    const currentVersion = i18nState.version;
    void currentVersion;

    const template = i18nState.messages[key] || fallback || key;
    if (!params || typeof params !== 'object') {
        return template;
    }
    return template.replace(/\{([^}]+)\}/g, (_, token) => {
        const value = params[token];
        return value === undefined || value === null ? '' : String(value);
    });
}

Vue.prototype.$i18nState = i18nState;
Vue.prototype.$i18n = function translateI18n(key, fallback = '', params = null) {
    return translateWithState(key, fallback, params);
};
Vue.prototype.$t = function translate(key, fallback = '', params = null) {
    return translateWithState(key, fallback, params);
};

SYNO.namespace('SYNO.SDS.App.AV_ImgData');

// Register the DSM app class synchronously. DSM expects it to exist immediately after bundle load.
SYNO.SDS.App.AV_ImgData.Instance = Vue.extend({
    components: { App },
    template: '<App/>',
});

createI18n()
    .then((i18n) => {
        i18nState.locale = i18n.locale;
        i18nState.messages = i18n.messages;
        i18nState.version += 1;
    })
    .catch(() => {
        // Keep the English fallback translator already installed above.
    });
