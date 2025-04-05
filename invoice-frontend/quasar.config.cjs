const { configure } = require('quasar/wrappers')

module.exports = configure(() => {
  return {
    framework: {
      config: {
        dark: false,
        brand: {
          primary: '#1976D2',
          secondary: '#26A69A',
          accent: '#9C27B0',
          dark: '#1D1D1D',
          positive: '#21BA45',
          negative: '#C10015',
          info: '#31CCEC',
          warning: '#F2C037'
        }
      },
      plugins: [
        'Notify',
        'Dialog',
        'Loading'
      ],
      extras: [
        'material-icons'
      ]
    },
    build: {
      vueRouterMode: 'hash',
      extendViteConf (viteConf) {
        viteConf.optimizeDeps = {
          ...(viteConf.optimizeDeps || {}),
          include: [
            'vue-pdf-embed'
          ]
        }
        viteConf.server = {
          ...(viteConf.server || {}),
          proxy: {
            '/api': {
              target: 'http://localhost:8000',
              changeOrigin: true,
              secure: false
            }
          }
        }
      }
    },
    devServer: {
      port: 8080,
      open: true
    }
  }
})
