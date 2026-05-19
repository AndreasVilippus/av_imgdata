export default {
	data() {
		return {
			operationPollStates: {},
		};
	},
	methods: {
		normalizeOperationPollKey(pollKey) {
			return String(pollKey || '').trim();
		},
		createOperationPollState() {
			return {
				inFlight: false,
				errorCount: 0,
				lastError: '',
				stoppedAfterErrors: false,
				lastSuccessAt: '',
				lastErrorAt: '',
			};
		},
		getOperationPollState(pollKey) {
			const normalizedPollKey = this.normalizeOperationPollKey(pollKey);
			if (!normalizedPollKey) {
				throw new Error('pollKey is required');
			}
			if (!this.operationPollStates || typeof this.operationPollStates !== 'object') {
				this.operationPollStates = {};
			}
			if (!this.operationPollStates[normalizedPollKey]) {
				this.operationPollStates = {
					...this.operationPollStates,
					[normalizedPollKey]: this.createOperationPollState(),
				};
			}
			return this.operationPollStates[normalizedPollKey];
		},
		resetOperationPollState(pollKey) {
			const state = this.getOperationPollState(pollKey);
			state.inFlight = false;
			state.errorCount = 0;
			state.lastError = '';
			state.stoppedAfterErrors = false;
			state.lastSuccessAt = '';
			state.lastErrorAt = '';
			return state;
		},
		resetOperationPollErrors(pollKey) {
			const state = this.getOperationPollState(pollKey);
			state.errorCount = 0;
			state.lastError = '';
			state.stoppedAfterErrors = false;
			state.lastSuccessAt = new Date().toISOString();
			return state;
		},
		recordOperationPollError(pollKey, err, { maxErrors = 3, onStopAfterErrors = null } = {}) {
			const state = this.getOperationPollState(pollKey);
			state.errorCount += 1;
			state.lastError = err && err.message ? err.message : String(err || 'Unknown polling error');
			state.lastErrorAt = new Date().toISOString();
			if (state.errorCount >= maxErrors) {
				state.stoppedAfterErrors = true;
				if (typeof onStopAfterErrors === 'function') {
					onStopAfterErrors(err, state);
				}
			}
			return state;
		},
		async runOperationPollRequest(pollKey, callback, options = {}) {
			const state = this.getOperationPollState(pollKey);
			const force = options.force === true;
			const maxErrors = Number(options.maxErrors) || 3;
			const onStopAfterErrors = options.onStopAfterErrors;

			if (state.inFlight && !force) {
				return { skipped: true };
			}

			state.inFlight = true;
			try {
				const result = await callback();
				state.errorCount = 0;
				state.lastError = '';
				state.stoppedAfterErrors = false;
				state.lastSuccessAt = new Date().toISOString();
				return result;
			} catch (err) {
				this.recordOperationPollError(pollKey, err, { maxErrors, onStopAfterErrors });
				return {};
			} finally {
				state.inFlight = false;
			}
		},
	},
};
