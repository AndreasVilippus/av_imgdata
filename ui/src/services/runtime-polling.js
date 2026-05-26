export function createRuntimePollingController(host) {
	const state = {
		pending: {},
		runIds: {},
	};

	function stopNamedPolling(timerKey) {
		if (host[timerKey]) {
			window.clearInterval(host[timerKey]);
			host[timerKey] = null;
		}
		state.pending[timerKey] = false;
		state.runIds[timerKey] = (Number(state.runIds[timerKey]) || 0) + 1;
	}

	function startNamedPolling(timerKey, callback, interval = 1000, options = {}) {
		stopNamedPolling(timerKey);
		const skipIfPending = options && options.skipIfPending === true;
		const runId = (Number(state.runIds[timerKey]) || 0) + 1;
		state.runIds[timerKey] = runId;
		const run = () => {
			if (skipIfPending && state.pending[timerKey]) {
				return;
			}
			state.pending[timerKey] = true;
			Promise.resolve()
				.then(() => callback())
				.catch(() => {})
				.finally(() => {
					if (state.runIds[timerKey] === runId) {
						state.pending[timerKey] = false;
					}
				});
		};
		run();
		host[timerKey] = window.setInterval(run, interval);
	}

	return {
		startNamedPolling,
		stopNamedPolling,
		_state: state,
	};
}
