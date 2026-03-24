const path = require('path');
const webpack = require('webpack');
const VueLoaderPlugin = require('vue-loader/lib/plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = async (env, argv) => {
	const isDevelopment = argv.mode === 'development';
	return {
		mode: isDevelopment ? 'development' : 'production',
		devtool: isDevelopment ? 'inline-source-map' : false,
		module: {
			rules: [
				{
					test: /\.vue$/,
					loader: 'vue-loader'
				},
				{
					exclude: /node_modules/,
					test: /\.js$/,
					use: {
						loader: 'babel-loader',
						options: {
							presets: ['@babel/preset-env']
						}
					}
				}, {
					test: /\.svg$/,
					type: 'asset/resource'
				}, {
					test: /\.css$/,
					use: [
						MiniCssExtractPlugin.loader,
						'css-loader'
					]
				}
			]
		},
		/* your package entry with Vue.extend and SYNO.namespace defined */
		entry: './src/main.js',
		output: {
			/* Need to write in config.define */
			filename: 'av-img-data.bundle.js',
			path: path.resolve('dist')
		},
		resolve: {
			extensions: ['.js', '.vue', '.json']
		},
		plugins: [
			new VueLoaderPlugin(),
			new MiniCssExtractPlugin({
			  filename: './style/av-img-data.bundle.css'
			})
		],
		externals: {
			'vue': 'Vue'
		},
		watchOptions: {
			poll: true
		},
	};
};
