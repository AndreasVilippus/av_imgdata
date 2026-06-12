export default {
	data() {
		return {
			musicRatingsLoading: false,
			musicRatingsMessage: '',
			musicRatingsCapabilities: {},
			musicRatingsSelectedUsers: [],
			musicRatingsChangedSinceDays: 0,
			musicRatingsLiveWatchEnabled: false,
			musicRatingsPreviewLoading: false,
			musicRatingsPreview: {},
		};
	},
	computed: {
		musicRatingsUsers() {
			const users = this.musicRatingsCapabilities && this.musicRatingsCapabilities.users;
			return users && Array.isArray(users.users) ? users.users : [];
		},
		musicRatingsSharedFolders() {
			return Array.isArray(this.musicRatingsCapabilities.shared_folders)
				? this.musicRatingsCapabilities.shared_folders
				: [];
		},
		musicRatingsAudioStation() {
			return this.musicRatingsCapabilities.audio_station || {};
		},
		musicRatingsScan() {
			return this.musicRatingsCapabilities.scan || {};
		},
	},
	methods: {
		async loadMusicRatingsCapabilities() {
			this.musicRatingsLoading = true;
			this.musicRatingsMessage = '';
			try {
				const response = await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/music_ratings_capabilities'
				);
				this.musicRatingsCapabilities = this.getResponseData(response);
				this.musicRatingsChangedSinceDays = Number(this.musicRatingsScan.changed_since_days_default) || 0;
				this.musicRatingsLiveWatchEnabled = !!this.musicRatingsScan.live_watch_enabled;
			} catch (err) {
				this.musicRatingsMessage = `Error: ${err.message}`;
			} finally {
				this.musicRatingsLoading = false;
			}
		},
		toggleMusicRatingsUser(userName) {
			const normalized = String(userName || '').trim();
			if (!normalized) {
				return;
			}
			if (this.musicRatingsSelectedUsers.includes(normalized)) {
				this.musicRatingsSelectedUsers = this.musicRatingsSelectedUsers.filter((name) => name !== normalized);
			} else {
				this.musicRatingsSelectedUsers = [...this.musicRatingsSelectedUsers, normalized];
			}
		},
		async loadMusicRatingsPreview() {
			this.musicRatingsPreviewLoading = true;
			this.musicRatingsMessage = '';
			try {
				const response = await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/music_ratings_preview',
					{ changed_since_days: this.musicRatingsChangedSinceDays, limit: 500 },
					{ timeoutMs: 120000 }
				);
				this.musicRatingsPreview = this.getResponseData(response);
			} catch (err) {
				this.musicRatingsMessage = `Error: ${err.message}`;
			} finally {
				this.musicRatingsPreviewLoading = false;
			}
		},
	},
};
