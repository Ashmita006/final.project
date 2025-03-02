fetch('/api/attendance')
  .then(response => response.json())
  .then(data => {
      console.log(data.attendance); // Log attendance data
  })
  .catch(error => console.error('Error fetching data:', error));
