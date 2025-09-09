window.addEventListener('load', function () {
  document.querySelectorAll('.changes-tabs').forEach((tabs) => {

    tabs.querySelector('.changes-tabs-label').classList.add('active')
    tabs.querySelector('.changes-tabs-content').classList.add('active')

    tabs.querySelector('.changes-tabs-labels').classList.add('active')

    tabs.querySelectorAll('.changes-tabs-label').forEach((label, index) => {
      label.addEventListener('click', () => {

        tabs.querySelectorAll('.changes-tabs-label').forEach((item) => {
          item.classList.remove('active')
        })
        tabs.querySelectorAll('.changes-tabs-content').forEach((item) => {
          item.classList.remove('active')
        })

        label.classList.add('active')
        tabs.querySelectorAll('.changes-tabs-content')[index].classList.add('active')

      })
    })
  })
})
