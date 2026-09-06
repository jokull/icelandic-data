from scripts.hagstofan_query import unpack

def test_sparse_json_stat_preserves_labels_and_nulls():
 meta={'variables':[{'code':'x','values':['a','b'],'valueTexts':['Þing','Önnur']} ]}
 data={'id':['x'],'size':[2],'dimension':{'x':{'category':{'index':{'b':1,'a':0}}}},'value':{'1':4}}
 assert unpack(data,meta)==[{'x':'a','labels':{'x':'Þing'},'value':None},{'x':'b','labels':{'x':'Önnur'},'value':4}]
